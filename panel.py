"""On-demand loopback desktop panel controller, independent of MCP client lifetime."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent


def ensure_panel(state, host, open_window=True):
    if os.environ.get("LOCAL_GRUNT_PANEL", "1") == "0": return
    if sys.platform != "darwin": return
    try:
        with (state / "panel-start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            descriptor = state / "panel.json"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def alive():
                try:
                    data = json.loads(descriptor.read_text())
                    with opener.open(data["url"].replace("/panel?", "/api/state?"), timeout=0.5) as r:
                        return r.status == 200
                except Exception: return False
            if not alive():
                with (state / "panel.log").open("a") as log:
                    subprocess.Popen([sys.executable, str(HERE / "dashboard.py"), "--state", str(state), "--host", host],
                                     stdout=subprocess.DEVNULL, stderr=log, start_new_session=True, close_fds=True)
                for _ in range(30):
                    if alive(): break
                    time.sleep(0.05)
                else: return
            app = HERE / "Local Grunt Adapter.app"
            if open_window and app.exists():
                subprocess.Popen(["/usr/bin/open", "-a", str(app), "--args", str(descriptor)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        # A display failure must never fail a useful local worker result.
        return
