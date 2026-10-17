"""Bounded, redacted observable actions from the native Hermes session store."""

import json
import re
import threading
from pathlib import Path
from typing import Any

from .core import WORKER, now, run, save

LOCK = threading.Lock()
# Read only public messages and tool records. Reasoning and system prompts stay out.
QUERY = """import json,sqlite3,sys
c=sqlite3.connect("file:/sandbox/.hermes/state.db?mode=ro",uri=True);c.row_factory=sqlite3.Row
wanted=set(json.loads(sys.argv[1])); workspace=sys.argv[2]
sessions=[dict(r) for r in c.execute("SELECT id,parent_session_id,cwd,model,api_call_count,input_tokens,output_tokens FROM sessions")]
wanted.update(r["id"] for r in sessions if r["cwd"]==workspace)
for _ in range(8):
 wanted.update(r["id"] for r in sessions if r["parent_session_id"] in wanted)
rows=[]
for sid in wanted:
 for r in c.execute("SELECT id,session_id,role,content,tool_call_id,tool_calls,tool_name,timestamp FROM messages WHERE session_id=? AND role IN ('assistant','tool') ORDER BY id LIMIT 2000",(sid,)):
  rows.append(dict(r))
rows.sort(key=lambda r:(r["timestamp"],r["id"]))
print(json.dumps({"sessions":[r for r in sessions if r["id"] in wanted],"messages":rows[:2000],"truncated":len(rows)>2000}))
"""
SECRET = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|password|secret|cookie)"
)
ASSIGNMENT = re.compile(
    r"""(?i)\b((?:[a-z0-9_]*(?:api[_-]?key|access[_-]?token|password|secret)|authorization|cookie)["']?\s*[:=]\s*["']?)([^\s,;"'}]+)"""
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if SECRET.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    text = re.sub(r"(?is)<think(?:ing)?>.*?</think(?:ing)?>", "", value)
    text = re.sub(r"(?is)<think(?:ing)?>.*$", "", text)
    text = re.sub(r"(?i)Bearer\s+[^\s\"'<>]+", "Bearer [redacted]", text)
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,})",
        "[redacted]",
        text,
    )
    return ASSIGNMENT.sub(r"\1[redacted]", text)


def bounded(value: Any) -> tuple[str, bool]:
    value = redact(value)
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, indent=2)
    )
    return text[:6000], len(text) > 6000


def public_trace(raw: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for message in raw.get("messages", []):
        common = {
            "session": message["session_id"],
            "at": message["timestamp"],
        }
        if message["role"] == "assistant" and message.get("tool_calls"):
            for index, call in enumerate(json.loads(message["tool_calls"])):
                function = call.get("function", {})
                arguments = function.get("arguments", "")
                try:
                    arguments = json.loads(arguments)
                except (ValueError, TypeError):
                    pass
                content, truncated = bounded(arguments)
                entries.append(
                    {
                        **common,
                        "id": f"{message['id']}:{index}",
                        "kind": "call",
                        "name": function.get("name", "tool"),
                        "call_id": call.get("id"),
                        "content": content,
                        "truncated": truncated,
                    }
                )
        elif message["role"] == "tool":
            content, truncated = bounded(message.get("content") or "")
            entries.append(
                {
                    **common,
                    "id": str(message["id"]),
                    "kind": "result",
                    "name": message.get("tool_name") or "tool",
                    "call_id": message.get("tool_call_id"),
                    "content": content,
                    "truncated": truncated,
                }
            )
        elif message["role"] == "assistant" and message.get("content"):
            content, truncated = bounded(message["content"])
            if content.strip():
                entries.append(
                    {
                        **common,
                        "id": str(message["id"]),
                        "kind": "message",
                        "name": "Hermes",
                        "content": content,
                        "truncated": truncated,
                    }
                )
    return {
        "captured_at": now(),
        "sessions": raw.get("sessions", []),
        "entries": entries,
        "truncated": raw.get("truncated", False),
    }


def capture(directory: Path) -> dict[str, Any]:
    session_ids = []
    for path in directory.glob("*-audit.json"):
        session_ids.extend(
            row["id"] for row in json.loads(path.read_text()).get("sessions", [])
        )
    containers = run(["docker", "ps", "--format", "{{.Names}}"], timeout=5).splitlines()
    matches = [
        name
        for name in containers
        if re.fullmatch(
            r"openshell-[a-zA-Z0-9_-]+--" + re.escape(WORKER) + r"-[a-f0-9-]+", name
        )
    ]
    if len(matches) != 1:
        raise RuntimeError("Native trace container is unavailable or ambiguous")
    raw = json.loads(
        run(
            [
                "docker",
                "exec",
                matches[0],
                "python3",
                "-c",
                QUERY,
                json.dumps(session_ids),
                "/sandbox/aya/" + directory.name,
            ],
            timeout=10,
        )
    )
    value = public_trace(raw)
    save(directory / "trace.json", value)
    return value


def read(directory: Path, refresh: bool = False) -> dict[str, Any]:
    path = directory / "trace.json"
    if (refresh or not path.exists()) and LOCK.acquire(blocking=False):
        try:
            return capture(directory)
        except Exception as exc:
            if not path.exists():
                return {"entries": [], "sessions": [], "error": str(exc)}
        finally:
            LOCK.release()
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"entries": [], "sessions": []}
    )


def monitor(directory: Path, stop: threading.Event) -> None:
    while not stop.wait(3):
        read(directory, refresh=True)
