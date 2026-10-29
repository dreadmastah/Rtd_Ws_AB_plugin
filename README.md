# Rtd_Ws_AB_plugin
## _AmiBroker Realtime data plugin using Websocket and JSON based communication_

[![Build Status](https://raw.githubusercontent.com/ideepcoder/Rtd_Ws_AB_plugin/84c47468847d2bbf53d2f12fa110d13c041d7b2d/images/unknown.svg)](https://github.com/ideepcoder/Rtd_Ws_AB_plugin)


## Features
- Bi-directional websocket communication
- Support to backfill historical data
- Easy to integrate Json message structure
- Run multiple instances of AmiBroker locally, each connected to one of multiple Servers
- The design makes it Broker / Data vendor agnostic
- Runs a python based relay server, to ensure individual connections don't disrupt your flow
- Build your own data routing logic
- Store your time-series data in the superfast Amibroker storage database
- Get you Realtime Quote window ticking as opposed to plain ASCII imports

# ✨ Upcoming  ✨
- ArcticDB active integration
- A lot of leverage with keeping bloated data locally in ArcticDB and a concise Amibroker database


## Documentation and manual
### -- Check Docs for the latest documentation

#### [Main Documentation](https://github.com/ideepcoder/Rtd_Ws_AB_plugin/blob/main/Docs/WSRTD%20Doc.md)
#### [Project Timeline](https://github.com/ideepcoder/Rtd_Ws_AB_plugin/blob/main/Docs/Project%20Timeline.md)

# .
## Licenses / Copyrights / Trademarks
##### This work incorporates materials copyrighted and trademarked by AmiBroker Company.
AmiBroker and the AmiBroker logo are trademarks of AmiBroker Company, used with permission.

<meta name="google-site-verification" content="P6lUDnSiQzdLc0o2hKTCqnrVbauXzN0wUsVwOr0pDRs" />

## WSRTD owned C++ plugin — architecture reference (R1, 2026-10-29)

The independently owned, database-bound C++ AmiBroker plugin is under native acceptance. The N1 DLL has been recognized and loaded in AmiBroker; dynamic symbol discovery, real-time status and watchlist reconciliation have offline test evidence, but automatic native watchlist updates, genuine Binance candle delivery and >500 concurrent streams are **not yet verified**. The two-symbol in-host watchlist procedure has been independently reviewed and is **ready for separate operator approval; it has not been executed**.

- [Architecture outline (Word DOCX)](Docs/WSRTD_Owned_CPP_Plugin_Architecture_Reference_R1_2026-10-29.docx)
- [Architecture outline (readable Markdown)](Docs/WSRTD_Owned_CPP_Architecture_R1.md)

These documents describe target architecture, evidence and remaining gates; they are not a production-release claim or authorization to change the legacy R2 installation.
