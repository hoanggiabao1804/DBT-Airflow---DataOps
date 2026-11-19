"""Tiny webhook receiver for testing DataOps alerts without Slack/Discord.

Listens for HTTP POSTs and appends each JSON body (plus arrival time) to a
JSON Lines file. Standard library only, so it runs inside the Airflow image:

    # inside a container on the Compose network (e.g. airflow-webserver)
    python /opt/airflow/scripts/alert_webhook_receiver.py --port 9099 --output /opt/airflow/logs/webhook_received.jsonl

    # then point Airflow at it (webserver + scheduler environment)
    DATAOPS_ALERT_WEBHOOK_URL=http://airflow-webserver:9099/alert

For local demos only: no authentication and no TLS.
"""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

LOCK = threading.Lock()


def make_handler(output):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(min(length, 1_000_000))
            try:
                body = json.loads(raw.decode("utf-8"))
            except ValueError:
                body = {"raw": raw.decode("utf-8", "replace")}
            record = {"received_at_utc": datetime.now(timezone.utc).isoformat(), "path": self.path, "body": body}
            with LOCK, output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"alert receiver up\n")

        def log_message(self, format, *args):  # noqa: A002 - signature from base class
            print("{} {}".format(self.address_string(), format % args), flush=True)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")  # nosec - local demo receiver
    parser.add_argument("--port", type=int, default=9099)
    parser.add_argument("--output", default="webhook_received.jsonl")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(output))
    print("Listening on {}:{} -> {}".format(args.host, args.port, output), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
