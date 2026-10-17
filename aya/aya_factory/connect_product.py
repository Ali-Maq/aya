"""Install the reviewed adapter into the separate local Open WebUI profile."""

import base64
import getpass
import json
import os
import urllib.error
import urllib.request
from typing import Any

from .core import MODEL, REPOSITORY, STATE, gh, run, save

ADAPTER_COMMIT = "68b18cbc69de3c4ba191570958a8ed142f7da1bb"


def request(path: str, token: str = "", payload: Any = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        "http://localhost:3032" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=90) as response:  # noqa: S310 — fixed local product origin
        return json.load(response)


def main() -> None:
    auth_path = STATE / "webui-auth.json"
    if auth_path.exists():
        auth = json.loads(auth_path.read_text())
    else:
        email = input("Open WebUI demo administrator email: ").strip()
        auth = request(
            "/api/v1/auths/signin",
            payload={"email": email, "password": getpass.getpass()},
        )
        save(auth_path, auth)
    token = auth["token"]
    identity = request("/api/v1/auths/", token)
    if identity["role"] != "admin":
        raise ValueError(
            "The demo profile needs an administrator for tool installation"
        )
    key = (
        os.environ.get("CRUSOE_API_KEY")
        or run(
            ["security", "find-generic-password", "-s", "crusoe-api-key", "-w"],
            timeout=10,
        ).strip()
    )
    request(
        "/openai/config/update",
        token,
        {
            "ENABLE_OPENAI_API": True,
            "OPENAI_API_BASE_URLS": ["https://api.inference.crusoecloud.com/v1"],
            "OPENAI_API_KEYS": [key],
            "OPENAI_API_CONFIGS": {"0": {"enable": True, "model_ids": [MODEL]}},
        },
    )
    content = gh(f"repos/{REPOSITORY}/contents/openwebui_tool.py?ref={ADAPTER_COMMIT}")
    adapter = base64.b64decode(content["content"]).decode()
    tool = {
        "id": "aya_recipes",
        "name": "AYA Saved Export Recipes",
        "content": adapter,
        "meta": {
            "description": "Export authorized JSON uploads through the verified AYA component."
        },
    }
    try:
        existing = request("/api/v1/tools/id/aya_recipes", token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        existing = None
    if existing and existing["user_id"] != identity["id"]:
        raise ValueError("An existing AYA tool belongs to another account")
    request(
        "/api/v1/tools/id/aya_recipes/update" if existing else "/api/v1/tools/create",
        token,
        tool,
    )
    model = {
        "id": "aya-data-recipes",
        "name": "AYA · JSON Recipes · Crusoe",
        "base_model_id": MODEL,
        "meta": {
            "description": "Saved JSON export recipes, recovered from jq and independently verified by AYA.",
            "toolIds": ["aya_recipes"],
            "capabilities": {
                "vision": False,
                "file_upload": True,
                "file_context": True,
            },
            "suggestion_prompts": [
                {
                    "title": ["List my recipes", "Show saved export recipes"],
                    "content": "Use the AYA tool to list my saved export recipes.",
                }
            ],
        },
        "params": {
            "function_calling": "native",
            "temperature": 0.1,
            "system": "You are the AYA JSON export assistant in Open WebUI. Use the AYA tools for every saved recipe or export action. Never fabricate CSV or download links. Save recipes with save_recipe. Use export_file with the uploaded file ID and recipe name. File IDs are in attachment context. Preserve the exact tool download link. Report when no verified module is available. jq fallback replaces null or false; null mode replaces only null.",
        },
        "is_active": True,
    }
    try:
        existing_model = request("/api/v1/models/model?id=aya-data-recipes", token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        existing_model = None
    request(
        "/api/v1/models/model/update?id=aya-data-recipes"
        if existing_model
        else "/api/v1/models/create",
        token,
        model,
    )
    installed = request("/api/v1/tools/id/aya_recipes", token)
    print(
        "Installed functions:", ", ".join(spec["name"] for spec in installed["specs"])
    )
    print("Product: http://localhost:3032 — select AYA · JSON Recipes · Crusoe")


if __name__ == "__main__":
    main()
