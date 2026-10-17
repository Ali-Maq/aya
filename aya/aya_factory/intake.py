"""Fetch live requests, then freeze their exact GitHub revisions."""

import base64
import json
import re
from typing import Any

from .core import REPOSITORY, gh, now, sha


def requests() -> dict[str, Any]:
    items = []
    page = 1
    while True:
        rows = gh(f"repos/{REPOSITORY}/issues?state=open&per_page=100&page={page}")
        items.extend(
            {
                "number": row["number"],
                "title": row["title"],
                "url": row["html_url"],
                "updated_at": row["updated_at"],
                "author": row["user"]["login"],
                "body": row.get("body") or "",
                "repository": REPOSITORY,
            }
            for row in rows
            if "pull_request" not in row
            and "aya:ready" in [label["name"] for label in row["labels"]]
        )
        if len(rows) < 100:
            break
        page += 1
        if page > 20:
            raise RuntimeError("Issue pagination limit exceeded")
    return {"fetched_at": now(), "source": "GitHub REST API", "requests": items}


def snapshot(number: int) -> dict[str, Any]:
    if type(number) is not int or number < 1:
        raise ValueError("Issue number must be a positive integer")
    issue = gh(f"repos/{REPOSITORY}/issues/{number}")
    if "pull_request" in issue or issue["state"] != "open":
        raise ValueError("Select an open feature issue")
    if issue["user"]["login"].lower() != "ali-maq" or "aya:ready" not in [
        x["name"] for x in issue["labels"]
    ]:
        raise ValueError("Only the repository owner's ready requests may run")
    body = issue.get("body") or ""
    target = re.search(r"^Target repository:\s*(\S+)\s*$", body, re.MULTILINE)
    contract = re.search(
        r"^Contract:\s*(specs/[a-z0-9-]+\.json)\s*$", body, re.MULTILINE
    )
    if not target or target[1] != REPOSITORY or not contract:
        raise ValueError(
            "Request must name the allowlisted target and a specs/*.json contract"
        )
    commit = gh(f"repos/{REPOSITORY}/commits/main")["sha"]
    content = gh(f"repos/{REPOSITORY}/contents/{contract[1]}?ref={commit}")
    raw = base64.b64decode(content["content"])
    spec = json.loads(raw)
    if (
        spec.get("target_repository") != REPOSITORY
        or spec.get("id") != "saved-json-export"
    ):
        raise ValueError("Unsupported target or feature contract")
    if spec.get("allowed_paths") != ["recipe.py", "tests/test_agent_recipe.py"]:
        raise ValueError("Contract attempts to change protected delivery paths")
    if sha(raw) != "b2f301300170295fd0a9236105d274ea88580b2beccf9289205c8a4c98763261":
        raise ValueError(
            "This contract revision needs evaluator review before it can run"
        )
    return {
        "fetched_at": now(),
        "issue": {
            "number": number,
            "node_id": issue["node_id"],
            "url": issue["html_url"],
            "title": issue["title"],
            "body": body,
            "updated_at": issue["updated_at"],
            "body_sha256": sha(body),
        },
        "target_repository": REPOSITORY,
        "target_base": commit,
        "contract_path": contract[1],
        "contract_commit": commit,
        "contract_sha256": sha(raw),
        "spec": spec,
        "policy_version": "aya-recipe-v1",
    }


def assert_current(frozen: dict[str, Any]) -> None:
    fresh = snapshot(frozen["issue"]["number"])
    if any(fresh[key] != frozen[key] for key in ["target_base", "contract_sha256"]):
        raise RuntimeError("Stale run: target or contract changed; start a new run")
    if (
        fresh["issue"]["body_sha256"] != frozen["issue"]["body_sha256"]
        or fresh["issue"]["updated_at"] != frozen["issue"]["updated_at"]
    ):
        raise RuntimeError("Stale run: GitHub issue changed; start a new run")
