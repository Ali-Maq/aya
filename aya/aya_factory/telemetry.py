"""Store redacted AYA trajectories through the installed Langfuse v3 API.

The local v3 service supports batch ingestion. A v4 deployment requires an OTLP
adapter. Credentials come from the environment or private .state/langfuse.json.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .core import STATE, now, save
from .trace import redact

MAX_ENTRIES = 2000
MAX_TEXT = 20000
EXCLUDED = re.compile(
    r"(?i)(hold.?out|held.?out|reasoning|chain.of.thought|thinking|system_prompt)"
)
NON_TRAINING_SPLITS = {"test", "holdout", "heldout", "held_out", "validation"}


@dataclass(frozen=True)
class Config:
    base_url: str
    public_key: str
    secret_key: str
    project_id: str


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        _req: urllib.request.Request,
        _fp: Any,
        _code: int,
        _msg: str,
        _headers: Any,
        _newurl: str,
    ) -> None:
        raise RuntimeError("Langfuse redirects are disabled")


def config() -> Config:
    path = STATE / "langfuse.json"
    local = json.loads(path.read_text()) if path.exists() else {}
    base = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    base = str(base or local.get("base_url", "http://127.0.0.1:3001")).rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Langfuse URL must not contain credentials or query parameters"
        )
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Langfuse requires HTTPS outside loopback")
    public = os.environ.get("LANGFUSE_PUBLIC_KEY") or local.get("public_key")
    secret = os.environ.get("LANGFUSE_SECRET_KEY") or local.get("secret_key")
    if not public or not secret:
        raise RuntimeError("Langfuse project API keys are not configured")
    return Config(
        base,
        str(public),
        str(secret),
        str(os.environ.get("LANGFUSE_PROJECT_ID") or local.get("project_id", "")),
    )


def request(settings: Config, path: str, body: Any = None) -> Any:
    credentials = base64.b64encode(
        f"{settings.public_key}:{settings.secret_key}".encode()
    ).decode()
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    req = urllib.request.Request(  # noqa: S310 — config permits HTTPS or loopback HTTP only
        settings.base_url + path,
        data=data,
        headers={
            "Authorization": "Basic " + credentials,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=8) as response:
        return json.loads(response.read(5_000_000))


def clean(value: Any) -> Any:
    """Remove private reasoning, secrets, and named evaluation-only content."""
    if isinstance(value, dict):
        if str(value.get("split", "")).lower() in NON_TRAINING_SPLITS:
            return {"omitted": "evaluation-only record"}
        return redact(
            {
                str(key): clean(item)
                for key, item in value.items()
                if not EXCLUDED.search(str(key))
            }
        )
    if isinstance(value, list):
        return [clean(item) for item in value[:MAX_ENTRIES]]
    if isinstance(value, str):
        text = str(redact(value))
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            text = json.dumps(clean(parsed), ensure_ascii=False)
        return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[truncated]"
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def identity(run_id: str, kind: str) -> str:
    return hashlib.sha256(f"aya:{run_id}:{kind}".encode()).hexdigest()[:32]


def project(payload: dict[str, Any]) -> dict[str, Any]:
    """Held-out runs expose aggregate metrics, never their task or action content."""
    metadata = payload.get("metadata", {})
    if str(metadata.get("split", "")).lower() not in NON_TRAINING_SPLITS:
        return clean(payload)
    return {
        "name": clean(payload.get("name", "AYA held-out evaluation")),
        "started_at": payload.get("started_at"),
        "input": {"omitted": "Held-out evaluation content"},
        "output": {"omitted": "Held-out evaluation content"},
        "metadata": {
            **{
                key: clean(metadata.get(key))
                for key in (
                    "split",
                    "framework",
                    "version_hash",
                    "dataset_hash",
                    "contract_hash",
                )
            },
            "eligible_for_training": False,
            "summary_only": True,
        },
        "scores": {
            key: value
            for key, value in payload.get("scores", {}).items()
            if key
            in {"heldout_accuracy", "accuracy", "passed", "total", "task_accuracy"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        },
        "generations": [],
        "trace": {"sessions": [], "entries": []},
    }


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(project(payload), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def timestamp(value: Any = None) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return now()


def event(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "timestamp": now(), "type": kind, "body": body}


def make_events(run_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    safe = project(payload)
    metadata = safe.get("metadata", {})
    trace_id = identity(run_id, "trace")
    started = timestamp(safe.get("started_at"))
    version = str(metadata.get("version_hash", ""))
    result = [
        event(
            "trace-create",
            {
                "id": trace_id,
                "timestamp": started,
                "name": safe.get("name", "AYA feature development"),
                "sessionId": "aya-" + run_id,
                "environment": "aya-local",
                "version": version,
                "tags": [
                    "AYA",
                    str(metadata.get("framework", "feature-recovery")),
                    str(metadata.get("split", "unspecified")),
                ],
                "public": False,
                "input": safe.get("input"),
                "output": safe.get("output"),
                "metadata": {
                    **metadata,
                    "run_id": run_id,
                    "trajectory_schema": "aya-v1",
                },
            },
        )
    ]
    if safe.get("workflow"):
        result.append(
            event(
                "event-create",
                {
                    "id": identity(run_id, "workflow"),
                    "traceId": trace_id,
                    "name": "Workflow instructions",
                    "startTime": started,
                    "environment": "aya-local",
                    "input": safe["workflow"],
                    "metadata": {"input_kind": "workflow_document"},
                },
            )
        )
    for index, generation in enumerate(safe.get("generations", [])[:MAX_ENTRIES]):
        if generation.get("omitted"):
            continue
        usage = generation.get("usage", {})
        result.append(
            event(
                "generation-create",
                {
                    "id": identity(run_id, f"generation:{index}"),
                    "traceId": trace_id,
                    "name": generation.get("name", f"generation-{index + 1}"),
                    "startTime": timestamp(generation.get("started_at") or started),
                    "endTime": timestamp(generation.get("ended_at") or started),
                    "environment": "aya-local",
                    "model": generation.get("model"),
                    "input": generation.get("prompt"),
                    "output": generation.get("completion"),
                    "metadata": {
                        "response_id": generation.get("response_id"),
                        "input_kind": generation.get("input_kind", "captured_prompt"),
                    },
                    "usage": {
                        "promptTokens": int(usage.get("prompt_tokens", 0)),
                        "completionTokens": int(usage.get("completion_tokens", 0)),
                        "totalTokens": int(usage.get("total_tokens", 0)),
                    },
                },
            )
        )
    native = safe.get("trace", {})
    result.extend(
        event(
            "span-create",
            {
                "id": identity(run_id, "session:" + str(session["id"])),
                "traceId": trace_id,
                "name": "Hermes session " + str(session["id"]),
                "startTime": started,
                "environment": "aya-local",
                "metadata": session,
                **(
                    {
                        "parentObservationId": identity(
                            run_id, "session:" + str(session["parent_session_id"])
                        )
                    }
                    if session.get("parent_session_id")
                    else {}
                ),
            },
        )
        for session in native.get("sessions", [])
    )
    for index, entry in enumerate(native.get("entries", [])[:MAX_ENTRIES]):
        if entry.get("omitted"):
            continue
        result.append(
            event(
                "event-create",
                {
                    "id": identity(
                        run_id,
                        "action:"
                        + str(entry.get("session"))
                        + ":"
                        + str(entry.get("id", index)),
                    ),
                    "traceId": trace_id,
                    "name": str(entry.get("name", "Hermes"))
                    + " · "
                    + str(entry.get("kind", "action")),
                    "startTime": timestamp(entry.get("at") or started),
                    "environment": "aya-local",
                    "parentObservationId": identity(
                        run_id, "session:" + str(entry.get("session"))
                    ),
                    "input" if entry.get("kind") == "call" else "output": entry.get(
                        "content"
                    ),
                    "metadata": {
                        key: entry.get(key)
                        for key in ("kind", "call_id", "session", "truncated")
                    },
                },
            )
        )
    for name, value in safe.get("scores", {}).items():
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            result.append(
                event(
                    "score-create",
                    {
                        "id": identity(run_id, "score:" + name),
                        "traceId": trace_id,
                        "name": name,
                        "value": value,
                        "dataType": "NUMERIC",
                        "environment": "aya-local",
                    },
                )
            )
    revision = payload_hash(payload)
    for row in result:
        row["body"]["metadata"] = {
            **row["body"].get("metadata", {}),
            "trajectory_revision": revision,
        }
    return result


def training_record(run_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Export only explicitly eligible development trajectories; never infer eligibility."""
    meta = payload.get("metadata", {})
    if (
        meta.get("split") not in {"dev", "development"}
        or meta.get("eligible_for_training") is not True
    ):
        return None
    if not all(
        meta.get(key) for key in ("version_hash", "dataset_hash", "contract_hash")
    ):
        return None
    return clean(
        {
            "run_id": run_id,
            **{
                key: payload.get(key)
                for key in (
                    "input",
                    "output",
                    "workflow",
                    "metadata",
                    "generations",
                    "trace",
                    "scores",
                )
            },
        }
    )


def record_run(runid: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Ingest a run, verify API readback, and retain an honest durable receipt."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", runid):
        raise ValueError("Invalid telemetry run ID")
    directory = STATE / "telemetry" / runid
    # Re-recording a run must revoke an older export until current checks pass.
    (directory / "training.json").unlink(missing_ok=True)
    receipt: dict[str, Any] = {"run_id": runid, "status": "error", "recorded_at": now()}
    try:
        settings = config()
        if not settings.project_id:
            projects = request(settings, "/api/public/projects")["data"]
            if len(projects) != 1:
                raise RuntimeError("Langfuse project ID is ambiguous")
            settings = Config(
                settings.base_url,
                settings.public_key,
                settings.secret_key,
                projects[0]["id"],
            )
        batch = make_events(runid, payload)
        revision = payload_hash(payload)
        trace_id = identity(runid, "trace")
        expected_ids = {
            row["body"]["id"]
            for row in batch
            if row["type"] not in {"trace-create", "score-create"}
        }
        expected_scores = {
            row["body"]["id"] for row in batch if row["type"] == "score-create"
        }
        receipt.update(
            trace_id=trace_id,
            trace_url=f"{settings.base_url}/project/{urllib.parse.quote(settings.project_id, safe='')}/traces/{trace_id}",
            observations=len(expected_ids),
            scores=len(expected_scores),
            trajectory_revision=revision,
        )
        # Twenty bounded records fit below the server's 3.5 MB ingestion limit.
        for offset in range(0, len(batch), 20):
            if len(json.dumps(batch[offset : offset + 20]).encode()) > 3_000_000:
                raise ValueError("Langfuse batch exceeds the safe ingestion size")
            response = request(
                settings,
                "/api/public/ingestion",
                {"batch": batch[offset : offset + 20]},
            )
            if response.get("errors"):
                raise RuntimeError(
                    "Langfuse ingestion rejected events: "
                    + json.dumps(clean(response["errors"]))
                )
        receipt["status"] = "accepted_pending"
        for attempt in range(8):
            if attempt:
                time.sleep(3)
            try:
                stored = request(settings, "/api/public/traces/" + trace_id)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            seen = {
                row["id"]
                for row in stored.get("observations", [])
                if row.get("metadata", {}).get("trajectory_revision") == revision
            }
            scores = {
                row["id"]
                for row in stored.get("scores", [])
                if row.get("metadata", {}).get("trajectory_revision") == revision
            }
            if project(payload).get("metadata", {}).get("summary_only") and stored.get(
                "observations"
            ):
                raise RuntimeError(
                    "Held-out trace contains earlier observations; delete that trace before summary ingestion"
                )
            if (
                stored.get("id") == trace_id
                and stored.get("metadata", {}).get("trajectory_revision") == revision
                and expected_ids <= seen
                and expected_scores <= scores
            ):
                receipt.update(
                    status="verified", verified_at=now(), observed_count=len(seen)
                )
                readback = clean(stored)
                if project(payload).get("metadata", {}).get("summary_only"):
                    readback = {
                        "id": stored["id"],
                        "metadata": {
                            **project(payload)["metadata"],
                            "trajectory_revision": revision,
                        },
                        "scores": [
                            {key: row.get(key) for key in ("id", "name", "value")}
                            for row in stored.get("scores", [])
                            if row["id"] in expected_scores
                        ],
                        "observations": [],
                        "input": {"omitted": "Held-out evaluation content"},
                        "output": {"omitted": "Held-out evaluation content"},
                    }
                save(directory / "readback.json", readback)
                break
        save(directory / "trajectory.json", project(payload))
        eligible = training_record(runid, payload)
        if eligible is not None and receipt["status"] == "verified":
            eligible.update(
                input=clean(stored.get("input")),
                output=clean(stored.get("output")),
                metadata=clean(stored.get("metadata", {})),
                provenance={
                    "source": "Langfuse API readback",
                    "trace_id": trace_id,
                    "trajectory_revision": revision,
                    "verified_at": receipt["verified_at"],
                },
            )
            save(directory / "training.json", eligible)
            receipt["training_export"] = str(directory / "training.json")
    except Exception as exc:
        receipt.update(status="error", error=str(clean(str(exc)))[:1000])
    receipt["receipt_path"] = str(directory / "receipt.json")
    save(directory / "receipt.json", receipt)
    return receipt
