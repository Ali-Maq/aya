"""Authenticated factory control and a separate narrow component endpoint."""

import hmac
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import intake, pipeline
from .core import ROOT, STATE, sha
from .evaluate import isolated

EXPORT_SLOTS = threading.BoundedSemaphore(2)


def load_environment() -> None:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("AYA_") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


class Handler(BaseHTTPRequestHandler):
    server_version = "AYA/0.1"

    def log_message(self, _format: str, *args: Any) -> None:
        print(
            f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}", flush=True
        )

    def send_json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, name: str) -> bool:
        expected = os.environ.get(name, "")
        if not expected or not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + expected
        ):
            self.send_json({"error": "Unauthorized"}, 401)
            return False
        return True

    def body(self, limit: int) -> Any:
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > limit:
            raise ValueError("Request size is outside the allowed range")
        return json.loads(self.rfile.read(size))

    def do_GET(self) -> None:
        if self.server.server_port != 8771:
            return self.send_json({"error": "Not found"}, 404)
        if not self.authorized("AYA_FACTORY_TOKEN"):
            return
        try:
            if self.path == "/requests":
                value = intake.requests()
            elif self.path == "/runs":
                value = pipeline.list_runs()
            elif re.fullmatch(r"/runs/[a-f0-9]{16}", self.path):
                value = pipeline.detail(self.path.rsplit("/", 1)[-1])
            else:
                return self.send_json({"error": "Not found"}, 404)
            self.send_json(value)
        except FileNotFoundError:
            self.send_json({"error": "Run not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 502)

    def do_POST(self) -> None:
        runtime = self.server.server_port == 8772
        if not self.authorized("AYA_RUNTIME_TOKEN" if runtime else "AYA_FACTORY_TOKEN"):
            return
        try:
            if not runtime and self.path == "/run":
                value = self.body(2048)
                if not isinstance(value, dict) or type(value.get("number")) is not int:
                    raise ValueError("Supply a GitHub issue number")
                return self.send_json(
                    pipeline.start(
                        value["number"],
                        self.headers.get("X-AYA-User", "local-operator"),
                    ),
                    202,
                )
            if runtime and self.path == "/export":
                payload = self.body(1_048_576)
                path = STATE / "deployment.json"
                if not path.exists():
                    return self.send_json(
                        {"error": "No verified module is deployed"}, 503
                    )
                deployed = json.loads(path.read_text())
                source = Path(deployed["path"]).read_text()
                if sha(source) != deployed["source_sha256"]:
                    raise RuntimeError("Deployed component digest mismatch")
                if not EXPORT_SLOTS.acquire(blocking=False):
                    return self.send_json({"error": "Export capacity reached"}, 429)
                try:
                    result = isolated(source, [payload], timeout=5)[0]
                finally:
                    EXPORT_SLOTS.release()
                if "error" not in result:
                    result["module_sha256"] = deployed["source_sha256"]
                    result["commit"] = deployed["commit"]
                return self.send_json(result)
            self.send_json({"error": "Not found"}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, 409)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 502)


def main() -> None:
    load_environment()
    control = ThreadingHTTPServer(("127.0.0.1", 8771), Handler)
    runtime = ThreadingHTTPServer(("127.0.0.1", 8772), Handler)
    # A restarted service must not silently claim it still owns an old job.
    for row in pipeline.list_runs():
        if row["status"] == "running":
            pipeline.state(
                pipeline.RUNS / row["id"],
                status="interrupted",
                stage="Interrupted",
                error="Factory service restarted; inspect the worker before retrying",
            )
    threading.Thread(target=runtime.serve_forever, daemon=True).start()
    print(
        "AYA control: 127.0.0.1:8771; component endpoint: :8772 (token required)",
        flush=True,
    )
    control.serve_forever()


if __name__ == "__main__":
    main()
