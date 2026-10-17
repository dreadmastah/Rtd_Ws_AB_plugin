import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import psutil

from Benchmarks.supervise_test_feed import acquire_mutex, kernel32, run


@unittest.skipUnless(sys.platform == 'win32', 'Windows process ownership')
class SupervisorTests(unittest.TestCase):
    def test_mutex_refuses_second_owner_then_releases(self):
        name = 'Local\\WSRTD_Unit_' + uuid.uuid4().hex
        first = acquire_mutex(name)
        try:
            self.assertIsNotNone(first)
            self.assertIsNone(acquire_mutex(name))
        finally:
            kernel32().CloseHandle(first)
        second = acquire_mutex(name)
        self.assertIsNotNone(second)
        kernel32().CloseHandle(second)

    def test_stop_file_prevents_any_process_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Binance').mkdir()
            (root / 'Relay/Server/Python').mkdir(parents=True)
            (root / 'Binance/sender.py').touch()
            (root / 'Relay/Server/Python/relay.py').touch()
            (root / 'selected-symbols.txt').write_text('BTCUSDT')
            (root / 'STOP').touch()
            run(root, root)
            self.assertFalse((root / 'status.json').exists())

    def test_supervisor_exit_kills_inherited_child(self):
        code = (
            'from Benchmarks.supervise_test_feed import contain_process_tree; '
            'import subprocess,sys,os,json,time; job=contain_process_tree(); '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],'
            'stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
            'print(json.dumps(dict(parent=os.getpid(),child=child.pid)),flush=True); time.sleep(60)'
        )
        helper = subprocess.Popen([sys.executable, '-B', '-c', code],
                                  creationflags=subprocess.CREATE_NO_WINDOW,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child = None
        parent = None
        try:
            # Native test runner is bounded externally; the helper prints only after job setup.
            line = helper.stdout.readline()
            if not line:
                _,error=helper.communicate(timeout=5)
                self.fail('No job receipt: '+error)
            receipt = json.loads(line)
            child = psutil.Process(receipt['child'])
            parent = psutil.Process(receipt['parent'])
            parent.terminate()
            deadline = time.monotonic() + 8
            while child.is_running() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertFalse(child.is_running(), 'Job left an orphan child')
            helper.wait(timeout=8)
        finally:
            for proc in (child, parent):
                if proc and proc.is_running():
                    proc.kill()
            if helper.poll() is None:
                helper.kill()
            helper.communicate(timeout=8)
