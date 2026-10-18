"""Read actual evidence from the contained REA MCP process."""

import json
import urllib.request
from typing import Any


class ReaClient:
    def __init__(self) -> None:
        self.session: str | None = None
        self.index = 0
        self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "aya-evidence", "version": "0.1"},
            },
        )
        self.rpc("notifications/initialized", {}, notification=True)

    def rpc(
        self, method: str, params: dict[str, Any], notification: bool = False
    ) -> Any:
        self.index += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.index
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        request = urllib.request.Request(
            "http://127.0.0.1:8766/mcp",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 — fixed HTTP(S) endpoint above
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            text = response.read(4_000_000).decode()
        if notification:
            return None
        messages = [
            json.loads(line[6:])
            for line in text.splitlines()
            if line.startswith("data: ")
        ]
        value = messages[-1] if messages else json.loads(text)
        if "error" in value:
            raise RuntimeError(str(value["error"]))
        return value["result"]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            payload = json.loads(
                next(c["text"] for c in result["content"] if c["type"] == "text")
            )
            error = payload.get("error", {})
            raise RuntimeError(
                f"REA {name}: {error.get('code', 'error')}: {error.get('message', 'Tool failed')}"
            )
        return json.loads(
            next(c["text"] for c in result["content"] if c["type"] == "text")
        )
