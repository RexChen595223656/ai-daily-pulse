#!/usr/bin/env python3
"""AI Daily — Dev server with pipeline refresh API.

Usage:
    python3 server.py              # Start on port 8080
    python3 server.py --port 3000  # Custom port
"""

import sys
import os
import json
import subprocess
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "pipeline" / "run.py"
DATA_DIR = ROOT / "data" / "daily"
LOCK = threading.Lock()
_pipeline_running = False

# Simple token to protect refresh endpoint (set via env or use default)
REFRESH_TOKEN = os.environ.get("AI_DAILY_REFRESH_TOKEN", "zhimai-refresh-2026")


class AIHandler(SimpleHTTPRequestHandler):
    """Serve static files + /api/refresh endpoint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path

        # API: refresh pipeline
        if path == "/api/refresh":
            self.handle_refresh()
            return

        # API: pipeline status
        if path == "/api/status":
            self.handle_status()
            return

        # Default: serve static files
        super().do_GET()

    def handle_status(self):
        global _pipeline_running
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        latest = "unknown"
        latest_path = DATA_DIR / "latest.json"
        if latest_path.exists():
            try:
                d = json.loads(latest_path.read_text(encoding="utf-8"))
                latest = d.get("date", "unknown")
            except Exception:
                pass

        self.wfile.write(json.dumps({
            "running": _pipeline_running,
            "latest_date": latest,
        }).encode())

    def handle_refresh(self):
        global _pipeline_running

        # Token check
        qs = parse_qs(urlparse(self.path).query)
        token = qs.get("token", [None])[0]
        if token != REFRESH_TOKEN:
            self.send_json(401, {"error": "Missing or invalid token"})
            return

        with LOCK:
            if _pipeline_running:
                self.send_json(409, {"error": "Pipeline already running"})
                return
            _pipeline_running = True

        self.send_json(202, {"status": "started", "message": "Pipeline started"})

        # Run pipeline in background thread
        def run():
            global _pipeline_running
            try:
                subprocess.run(
                    [sys.executable, str(PIPELINE)],
                    cwd=str(ROOT),
                    capture_output=True,
                    timeout=120,
                )
            except Exception as e:
                print(f"[pipeline] Error: {e}")
            finally:
                _pipeline_running = False

        threading.Thread(target=run, daemon=True).start()

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        # Quieter logging
        if "/api/" in str(args[0]):
            print(f"[api] {args[0]}")
        else:
            pass  # Suppress static file logs


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), AIHandler)
    print(f"AI Daily server → http://localhost:{args.port}/prototype/index.html")
    print(f"  Refresh API: POST /api/refresh  |  Status: GET /api/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
