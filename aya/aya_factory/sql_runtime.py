"""Live GitHub data and the independently accepted SQL deployment."""

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from . import sql_client, sql_eval
from .core import STATE, gh, now, run, save, sha

REPOS = [
    "fw-ai/cookbook",
    "crusoecloud/crusoe-cookbook",
    "crusoecloud/crusoe-developer-hub",
    "perplexityai/api-cookbook",
    "youdotcom-oss/agent-skills",
    "youdotcom-oss/ydc-research-sample",
]
SLOTS = threading.BoundedSemaphore(2)


def key() -> str:
    return (
        os.environ.get("CRUSOE_API_KEY")
        or run(
            ["security", "find-generic-password", "-s", "crusoe-api-key", "-w"],
            timeout=10,
        ).strip()
    )


def records() -> list[dict[str, Any]]:
    rows = []
    for repository in REPOS:
        value = gh("repos/" + repository)
        rows.append(
            {
                "repo": value["full_name"],
                "owner": value["owner"]["login"],
                "stars": value["stargazers_count"],
                "forks": value["forks_count"],
                "issues": value["open_issues_count"],
                "license": (value.get("license") or {}).get("spdx_id"),
                "description": value.get("description"),
                "url": value["html_url"],
            }
        )
    return rows


def deployment() -> dict[str, Any] | None:
    path = STATE / "sql-deployment.json"
    if not path.exists():
        return None
    return {k: v for k, v in json.loads(path.read_text()).items() if k != "path"}


def ask(question: str) -> dict[str, Any]:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        raise ValueError("Ask a question of 1 to 1000 characters")
    path = STATE / "sql-deployment.json"
    if not path.exists():
        raise RuntimeError("Build and verify the repository analyst first")
    if not SLOTS.acquire(blocking=False):
        raise RuntimeError("Two live questions are already running")
    try:
        deployed = json.loads(path.read_text())
        source = Path(deployed["path"]).read_text()
        if sha(source) != deployed["source_sha256"]:
            raise RuntimeError("Deployed SQL component digest mismatch")
        data = records()
        result = sql_client.ask(
            question,
            data,
            key(),
            lambda payload: sql_eval.isolated(source, [payload], timeout=8)[0],
        )
        result.update(
            {
                "fetched_at": now(),
                "sources": [row["url"] for row in data],
                "commit": deployed["commit"],
                "module_sha256": sha(source),
                "pr_url": deployed["pr_url"],
            }
        )
        save(
            STATE / "questions" / (uuid.uuid4().hex + ".json"),
            {"question": question, "records": data, "result": result},
        )
        return result
    finally:
        SLOTS.release()
