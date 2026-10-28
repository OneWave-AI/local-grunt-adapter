"""Private loopback-only UI service. Starts on demand and expires after idle time."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.parse
import urllib.request
from jobs import Jobs
from telemetry import Ledger
from runtime import memory_snapshot

HERE = Path(__file__).resolve().parent


def create_server(state, host="http://127.0.0.1:11434", token=None):
    token = token or secrets.token_urlsafe(32)
    jobs = Jobs(state)
    state = Path(state)
    config = urllib.parse.urlparse(host)
    if config.scheme != "http" or config.hostname not in {"127.0.0.1", "localhost", "::1"} or config.path not in {"", "/"} or config.username or config.password or config.query or config.fragment:
        raise ValueError("Panel backend must be loopback Ollama")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Panel backend redirects are disabled")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    backend = {"at": 0, "models": [], "available": True}
    backend_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            expected_host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            supplied = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if self.headers.get("Host") != expected_host or (origin and origin != "http://" + expected_host) or not hmac.compare_digest(supplied, token):
                self.send_error(403); return
            self.server.last_request = time.monotonic()
            if parsed.path == "/api/state":
                with backend_lock:
                    if time.monotonic()-backend["at"] > 3:
                        try:
                            with opener.open(host.rstrip("/") + "/api/ps", timeout=1) as r:
                                data = json.loads(r.read(200000))
                            backend.update(models=[{"name": m.get("name"), "bytes": m.get("size_vram", m.get("size", 0)), "context": m.get("context_length"), "runner": m.get("runner", m.get("details", {}).get("runner", "Ollama")), "quantization": m.get("details", {}).get("quantization_level", "")} for m in data.get("models", [])], available=True)
                        except Exception: backend.update(models=[], available=False)
                        backend["at"] = time.monotonic()
                    snapshot = dict(backend)
                payload = {"jobs": jobs.snapshot(), "memory": memory_snapshot(), "loaded_models": snapshot["models"], "backend_available": snapshot["available"], "now": time.time(), "usage": Ledger(state / "usage.sqlite3").summary()}
                body = json.dumps(payload).encode(); mime = "application/json"
            elif parsed.path == "/panel":
                body = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local Grunt Adapter</title>'
                        '<style>html,body{margin:0;height:100%;background:#0b0e12}iframe{border:0;width:100%;height:calc(100% - 28px);margin-top:28px;display:block}</style></head>'
                        '<body><iframe title="Local Grunt Adapter activity" sandbox="allow-scripts allow-same-origin" src="/ui?token=' + token + '"></iframe></body></html>').encode(); mime = "text/html; charset=utf-8"
            elif parsed.path == "/ui":
                page = (HERE / "desktop" / "dashboard.html").read_text()
                script = (HERE / "desktop" / "dashboard.js").read_text()
                body = page.replace("<!--DASHBOARD_SCRIPT-->", "<script>" + script + "</script>").encode(); mime = "text/html; charset=utf-8"
            else: self.send_error(404); return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.last_request = time.monotonic()
    server.daemon_threads = True
    server.panel_token = token
    return server


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True)
    p.add_argument("--host", default="http://127.0.0.1:11434")
    args = p.parse_args()
    state = Path(args.state)
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    server = create_server(state, args.host)
    descriptor = state / "panel.json"
    temp = state / "panel.json.tmp"
    temp.write_text(json.dumps({"pid": os.getpid(), "url": f"http://127.0.0.1:{server.server_port}/panel?token={server.panel_token}"}))
    temp.chmod(0o600); temp.replace(descriptor)
    def expire():
        while True:
            time.sleep(20)
            if time.monotonic()-server.last_request > 900 and not any(j["finished"] is None for j in Jobs(state).snapshot()):
                server.shutdown(); return
    threading.Thread(target=expire, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__": main()
