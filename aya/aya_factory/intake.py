"""Fetch live requests, then freeze their exact GitHub revisions."""

import base64
import json
import re
from typing import Any

from .core import REPOSITORY, gh, now, run, sha
from .profiles import catalog, for_repository


def requests() -> dict[str, Any]:
    items = []
    for profile in catalog():
        items.extend(repository_requests(profile["repository"]))
    return {
        "fetched_at": now(),
        "source": "GitHub REST API",
        "requests": items,
        "profiles": catalog(),
    }


def repository_requests(repository: str) -> list[dict[str, Any]]:
    items = []
    page = 1
    while True:
        rows = gh(f"repos/{repository}/issues?state=open&per_page=100&page={page}")
        items.extend(
            {
                "number": row["number"],
                "title": row["title"],
                "url": row["html_url"],
                "updated_at": row["updated_at"],
                "author": row["user"]["login"],
                "body": row.get("body") or "",
                "repository": repository,
                "ready": "aya:ready" in [label["name"] for label in row["labels"]],
            }
            for row in rows
            if "pull_request" not in row
            and any(
                label["name"] in {"aya:ready", "aya:proposal"}
                for label in row["labels"]
            )
        )
        if len(rows) < 100:
            break
        page += 1
        if page > 20:
            raise RuntimeError("Issue pagination limit exceeded")
    return items


def snapshot(number: int, repository: str = REPOSITORY) -> dict[str, Any]:
    profile = for_repository(repository)
    if type(number) is not int or number < 1:
        raise ValueError("Issue number must be a positive integer")
    issue = gh(f"repos/{repository}/issues/{number}")
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
    if (
        not target
        or target[1] != repository
        or not contract
        or contract[1] != profile["contract_path"]
    ):
        raise ValueError(
            "Request must name the allowlisted target and a specs/*.json contract"
        )
    commit = gh(f"repos/{repository}/commits/main")["sha"]
    content = gh(f"repos/{repository}/contents/{contract[1]}?ref={commit}")
    raw = base64.b64decode(content["content"])
    spec = json.loads(raw)
    if spec.get("target_repository") != repository or spec.get("id") != profile["id"]:
        raise ValueError("Unsupported target or feature contract")
    if spec.get("allowed_paths") != profile["allowed_paths"]:
        raise ValueError("Contract attempts to change protected delivery paths")
    if sha(raw) != profile["contract_sha256"]:
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
        "target_repository": repository,
        "profile": profile["id"],
        "target_base": commit,
        "contract_path": contract[1],
        "contract_commit": commit,
        "contract_sha256": sha(raw),
        "spec": spec,
        "policy_version": "aya-" + profile["id"] + "-v1",
    }


def assert_current(frozen: dict[str, Any]) -> None:
    fresh = snapshot(frozen["issue"]["number"], frozen["target_repository"])
    if any(fresh[key] != frozen[key] for key in ["target_base", "contract_sha256"]):
        raise RuntimeError("Stale run: target or contract changed; start a new run")
    if (
        fresh["issue"]["body_sha256"] != frozen["issue"]["body_sha256"]
        or fresh["issue"]["updated_at"] != frozen["issue"]["updated_at"]
    ):
        raise RuntimeError("Stale run: GitHub issue changed; start a new run")


def create_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Supply a repository, feature, and reference")
    if not isinstance(value.get("repository"), str):
        raise ValueError("Supply a repository name")
    repository = (
        value.get("repository", "")
        .strip()
        .removeprefix("https://github.com/")
        .removesuffix("/")
    )
    profile = for_repository(repository)
    feature, reference = value.get("feature", ""), value.get("reference", "")
    if (
        not isinstance(feature, str)
        or not 10 <= len(feature.strip()) <= 4000
        or not isinstance(reference, str)
        or not 1 <= len(reference.strip()) <= 2000
    ):
        raise ValueError("Supply a feature of 10–4000 characters and a reference URL")
    feature, reference = feature.strip(), reference.strip()
    if not reference.startswith("https://"):
        raise ValueError("Reference must be an HTTPS URL")
    ready = feature == profile["feature"] and reference == profile["reference"]
    title = profile["title"] if ready else feature.splitlines()[0][:120]
    body = (
        feature
        + "\n\nTarget repository: "
        + repository
        + "\nReference: "
        + reference
        + "\n"
        + (
            "Contract: " + profile["contract_path"] + "\n"
            if ready
            else "Status: Proposal; independent contract review required before execution.\n"
        )
    )
    result = json.loads(
        run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repository}/issues",
                "--input",
                "-",
            ],
            data=json.dumps(
                {
                    "title": title,
                    "body": body,
                    "labels": ["aya:ready" if ready else "aya:proposal"],
                }
            ),
            timeout=35,
        )
    )
    return {
        "number": result["number"],
        "url": result["html_url"],
        "repository": repository,
        "ready": ready,
    }
