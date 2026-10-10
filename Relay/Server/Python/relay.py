'''
//      #####   Relay_Server.py   #####
//
// Independent Relay server for WsRtd AmiBroker Data Plugin
//
// Central Websocket Python Program that runs as a Server.
// Both, CLient Application RTD Senders and the WsRTD data plugin
// connect to this server via specified IP:Port
//
// The advantage is that either Sender-Client or Receiver-client
// can restart or drop the connection without affecting the other.
// In the future, it will also serve to hook ArcticDB integration into the system.
//
///////////////////////////////////////////////////////////////////////
// Author: NSM51
// https://github.com/ideepcoder/Rtd_Ws_AB_plugin/
// https://forum.amibroker.com/u/nsm51/summary
//
// Users and possessors of this source code are hereby granted a nonexclusive,
// royalty-free copyright license to use this code in individual and commercial software.
//
// AUTHOR ( NSM51 ) MAKES NO REPRESENTATION ABOUT THE SUITABILITY OF THIS SOURCE CODE FOR ANY PURPOSE.
// IT IS PROVIDED "AS IS" WITHOUT EXPRESS OR IMPLIED WARRANTY OF ANY KIND.
// AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOURCE CODE,
// INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
// IN NO EVENT SHALL AUTHOR BE LIABLE FOR ANY SPECIAL, INDIRECT, INCIDENTAL, OR
// CONSEQUENTIAL DAMAGES, OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
// WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
// ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOURCE CODE.
//
// Any use of this source code must include the above notice,
// in the user documentation and internal comments to the code.
'''


# Each peer has one writer: slow receivers cannot block the upstream reader.
import argparse
import asyncio
import logging
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

LOG = logging.getLogger("relay")

class Relay:
    def __init__(self, queue_size=256, protocol="role"):
        if protocol not in ("role", "path"):
            raise ValueError("Unknown relay protocol")
        self.protocol = protocol
        self.clients = {}
        self.senders = {}
        self.queue_size = queue_size
        self.forwarded = 0
        self.overflows = 0

    async def writer(self, ws, queue):
        while True:
            await asyncio.wait_for(ws.send(await queue.get()), timeout=10)

    async def broadcast(self, peers, message):
        for ws, queue in tuple(peers.items()):
            try:
                queue.put_nowait(message)
                self.forwarded += 1
            except asyncio.QueueFull:
                # Never silently drop history or final candles. Force reconnect/backfill.
                self.overflows += 1
                peers.pop(ws, None)
                asyncio.create_task(ws.close(1013, "Slow peer; reconnect and backfill"))
                LOG.warning("peer queue overflow count=%s", self.overflows)

    async def handler(self, ws):
        peers = None
        writer = None
        try:
            if self.protocol == "path":
                # Explicit opt-in for CleanRoomR2: the native receiver sends no
                # role handshake. Never guess this mode after a timeout.
                path = ws.request.path
                if path in ("/", "/receiver"):
                    role = "rolerecv"
                elif path == "/sender":
                    role = "rolesend"
                else:
                    await ws.close(1008, "Unknown role path")
                    return
            else:
                role = await asyncio.wait_for(ws.recv(), 10)
            if role in ("rolesend", "--rolesend"):
                peers, targets = self.senders, self.clients
            elif role in ("rolerecv", "--rolerecv"):
                peers, targets = self.clients, self.senders
            else:
                await ws.close(1008, "Expected rolesend or rolerecv")
                return
            queue = asyncio.Queue(self.queue_size)
            peers[ws] = queue
            writer = asyncio.create_task(self.writer(ws, queue))
            async def reader():
                async for message in ws:
                    if self.protocol == "path" and message in (
                            "rolesend", "--rolesend", "rolerecv", "--rolerecv"):
                        if message.lstrip("-") != role:
                            await ws.close(1008, "Role conflicts with path")
                            return
                        continue
                    if message in ("zzz", "close"):
                        LOG.info("Ignored legacy shutdown command")
                        continue
                    await self.broadcast(targets, message)
            reader_task = asyncio.create_task(reader())
            try:
                done, _ = await asyncio.wait((reader_task, writer), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                reader_task.cancel()
                await asyncio.gather(reader_task, return_exceptions=True)
        except (ConnectionClosed, TimeoutError):
            pass
        finally:
            if peers is not None:
                peers.pop(ws, None)
            if writer is not None:
                writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
            await ws.close()

async def run(port=10101, queue_size=256, protocol="role"):
    relay = Relay(queue_size, protocol)
    async with serve(relay.handler, "127.0.0.1", port, compression=None,
                     max_size=4 * 1024 * 1024, max_queue=32):
        LOG.info("Relay listening on 127.0.0.1:%s", port)
        await asyncio.Future()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=10101)
    parser.add_argument("action", nargs="?", choices=["startserver"], default="startserver")
    parser.add_argument("--queue-size", type=int, default=256)
    parser.add_argument("--protocol", choices=["role", "path"], default="role",
                        help="path: CleanRoomR2 root receiver and /sender; loopback only")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.queue_size < 1:
        parser.error("invalid port or queue size")
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run(args.port, args.queue_size, args.protocol))
    except KeyboardInterrupt:
        pass
