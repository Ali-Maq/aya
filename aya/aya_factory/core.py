"""Process bounds, durable receipts, and the host integration boundary."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
STATE.mkdir(parents=True, exist_ok=True)
REPOSITORY = "Ali-Maq/aya-data-recipes"
WORKER = os.environ.get("AYA_WORKER", "aya-feature")
MODEL = "deepseek-ai/DeepSeek-V4-Pro"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(
    args: list[str],
    *,
    data: str | None = None,
    timeout: int = 60,
    cwd: Path | None = None,
    log: Path | None = None,
    env: dict[str, str] | None = None,
    limit: int = 4_000_000,
) -> str:
    """Keep output bounded and terminate the owned process group on timeout."""
    with (
        tempfile.TemporaryFile() as out,
        tempfile.TemporaryFile() as err,
        tempfile.TemporaryFile() as inp,
    ):
        if data is not None:
            inp.write(data.encode())
            inp.seek(0)
        process = subprocess.Popen(
            args,
            stdin=inp,
            stdout=out,
            stderr=err,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"{args[0]} exceeded {timeout} seconds")
                if out.tell() + err.tell() > limit:
                    raise RuntimeError("Process output limit exceeded")
                time.sleep(0.1)
            out.seek(0)
            err.seek(0)
            stdout, stderr = (
                out.read(limit + 1).decode(errors="replace"),
                err.read(limit + 1).decode(errors="replace"),
            )
            if process.returncode:
                raise RuntimeError(
                    f"{args[0]} failed ({process.returncode}): {stderr[-1200:]}"
                )
            if len(stdout.encode()) + len(stderr.encode()) > limit:
                raise RuntimeError("Process output limit exceeded")
            return stdout
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            if log:
                log.parent.mkdir(parents=True, exist_ok=True)
                out.seek(0)
                err.seek(0)
                log.with_suffix(".stdout.log").write_text(
                    out.read(limit).decode(errors="replace")
                )
                log.with_suffix(".stderr.log").write_text(
                    err.read(limit).decode(errors="replace")
                )


def gh(endpoint: str) -> Any:
    return json.loads(run(["gh", "api", endpoint], timeout=35))


class Journal:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **fields: Any) -> None:
        record = {"at": now(), "event": event, **fields}
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(record), flush=True)


def events(directory: Path) -> list[dict[str, Any]]:
    path = directory / "events.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )
