"""Prepare, then explicitly deploy and evaluate one bounded Crusoe checkpoint.

Management schema: https://docs.crusoecloud.com/api/
Lifecycle: https://docs.crusoecloud.com/self-serve-deployments/quickstart/index.html
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

import httpx

from . import sql_benchmark, sql_runtime, training
from .core import ROOT, STATE, now, save, sha
from .trace import redact

PROJECT = "2170c826-5bdc-4d7b-b8b8-8c3378e802b5"
FLAVOR = "aa2baad4-5f6f-40ff-9ff1-9898d5438adb"
MANAGEMENT = f"https://api.crusoecloud.com/v1/projects/{PROJECT}/foundry/selfserve"
INFERENCE = "https://api.inference.crusoecloud.com/v1/chat/completions"
MAX_SECONDS = 3600
CLEANUP_RESERVE = 60
STATES = {
    "creating",
    "ready",
    "scaling up",
    "scaling down",
    "syncing",
    "failed",
    "deleting",
    "deleted",
}


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(
            headers={"Authorization": "Bearer " + sql_runtime.key()},
            timeout=20,
            trust_env=False,
            follow_redirects=False,
        )

    def request(
        self, method: str, path: str, body: Any = None, timeout: float = 20
    ) -> dict[str, Any]:
        response = self.http.request(
            method, MANAGEMENT + path, json=body, timeout=timeout
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self.http.close()


def directory_for(run_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{16}", run_id):
        raise ValueError("Invalid experiment ID")
    directory = STATE / "mass" / run_id
    if not (directory / "training/job.json").is_file():
        raise FileNotFoundError("Training job receipt is missing")
    return directory


def validate_budget(seconds: int) -> None:
    if type(seconds) is not int or not 120 <= seconds <= MAX_SECONDS:
        raise ValueError("Deployment lifetime must be 120..3600 seconds")


def job_binding(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: job.get(key)
        for key in (
            "id",
            "status",
            "model",
            "fine_tuned_model",
            "training_file",
            "validation_file",
            "trained_tokens",
        )
    }


def digest(value: Any) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")))


def selected_flavor(flavors: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in flavors if item.get("id") == FLAVOR]
    if len(matches) != 1:
        raise RuntimeError("The approved deployment flavor is unavailable")
    item = matches[0]
    if (
        item.get("model_name") != training.STUDENT
        or item.get("gpu_type") != "h100"
        or item.get("gpus_per_instance") != 1
        or item.get("quantization") != "bf16"
        or item.get("fused_lora_supported") is not True
        or item.get("lora_suitable") is not True
    ):
        raise RuntimeError(
            "The selected flavor no longer matches the checkpoint recipe"
        )
    price = Decimal(str(item["price_per_hour"]))
    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid deployment price")
    return item


def recipe(
    directory: Path, job: dict[str, Any], flavors: list[dict[str, Any]], seconds: int
) -> dict[str, Any]:
    validate_budget(seconds)
    flavor = selected_flavor(flavors)
    model = job.get("fine_tuned_model")
    ready = job.get("status") == "succeeded" and isinstance(model, str) and bool(model)
    value: dict[str, Any] = {
        "run_id": directory.name,
        "status": "ready_for_approval" if ready else "awaiting_checkpoint",
        "project_id": PROJECT,
        "job": job_binding(job),
        "job_binding_sha256": digest(job_binding(job)),
        "max_seconds": seconds,
        "hourly_cost_usd": str(flavor["price_per_hour"]),
        "estimated_lifetime_cost_usd": str(
            (Decimal(str(flavor["price_per_hour"])) * seconds / 3600).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING
            )
        ),
        "request": {
            "deployment_name": "aya-sql-" + directory.name,
            "fine_tuned_model": model,
            "flavor_id": FLAVOR,
            "replicas": 1,
        },
        "hardware": {
            key: flavor[key]
            for key in ("model_name", "gpu_type", "gpus_per_instance", "quantization")
        },
        "inference_endpoint": INFERENCE,
        "cleanup": "Delete the owned deployment after evaluation or before the lifetime deadline; independent local watchdog also attempts cleanup.",
        "cost_limit": "Runtime estimate, not a provider billing cap. Host or API failure can delay deletion and extend billing.",
        "evaluation": "12 held-out questions on three frozen datasets; no improvement claim without a matched base-student comparison.",
        "schema_source": "https://docs.crusoecloud.com/api/",
        "lifecycle_source": "https://docs.crusoecloud.com/self-serve-deployments/quickstart/index.html",
    }
    value["recipe_sha256"] = digest(value)
    return value


def prepare(directory: Path, seconds: int = 2700) -> dict[str, Any]:
    """Read-only provider discovery; never create a deployment."""
    validate_budget(seconds)
    if (directory / "training/deployment/creation-started.json").exists():
        raise RuntimeError("An attempted deployment recipe cannot be overwritten")
    api = Client()
    try:
        catalog = api.request("GET", "/flavors")
        existing = api.request("GET", "/deployments")
    finally:
        api.close()
    job = json.loads((directory / "training/job.json").read_text())
    plan = recipe(directory, job, catalog["flavors"], seconds)
    destination = directory / "training/deployment"
    save(destination / "flavors.json", catalog)
    save(destination / "existing.json", existing)
    save(destination / "recipe.json", plan)
    return plan


def deployment_state(value: dict[str, Any]) -> str:
    status = str(value.get("status", "")).strip().casefold()
    if status not in STATES:
        raise ValueError("Undocumented deployment status: " + status[:100])
    return status


def verify_owned(value: dict[str, Any], plan: dict[str, Any], resource_id: str) -> None:
    expected = plan["request"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", resource_id):
        raise ValueError("Invalid deployment identifier")
    if (
        value.get("id") != resource_id
        or value.get("deployment_name") != expected["deployment_name"]
        or value.get("fine_tuned_model") != expected["fine_tuned_model"]
        or value.get("target_replicas") != 1
    ):
        raise RuntimeError("Deployment identity differs from the owned resource")


def discover_owned(api: Client, destination: Path, plan: dict[str, Any]) -> str | None:
    creation = json.loads((destination / "creation-started.json").read_text())
    before = set(creation["prior_ids"])
    start = datetime.fromisoformat(creation["started_at"])
    matches = []
    for row in api.request("GET", "/deployments", timeout=5).get("deployments", []):
        if (
            row.get("id") in before
            or row.get("deployment_name") != plan["request"]["deployment_name"]
            or row.get("fine_tuned_model") != plan["request"]["fine_tuned_model"]
        ):
            continue
        created = datetime.fromisoformat(row["created_at"])
        if created.tzinfo is None or created < start:
            continue
        verify_owned(row, plan, row["id"])
        matches.append(row)
    if len(matches) > 1:
        raise RuntimeError("Deployment ownership is ambiguous")
    if not matches:
        return None
    save(destination / "creation-reconciled.json", matches[0])
    return str(matches[0]["id"])


def cleanup(directory: Path) -> dict[str, Any]:
    """Delete only a resource proven to belong to this recorded create request."""
    destination = directory / "training/deployment"
    with (destination / "cleanup.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX)
        prior = destination / "cleanup.json"
        if prior.exists() and json.loads(prior.read_text()).get("status") == "deleted":
            return json.loads(prior.read_text())
        plan = json.loads((destination / "recipe.json").read_text())
        creation = json.loads((destination / "creation-started.json").read_text())
        unsigned = {key: value for key, value in plan.items() if key != "recipe_sha256"}
        if digest(unsigned) != creation["recipe_sha256"]:
            raise RuntimeError(
                "Cleanup recipe differs from the recorded create request"
            )
        receipt: dict[str, Any] = {"started_at": now(), "status": "cleanup_required"}
        api = Client()
        try:
            created = destination / "created.json"
            resource_id = (
                json.loads(created.read_text()).get("id")
                if created.exists()
                else discover_owned(api, destination, plan)
            )
            receipt["deployment_id"] = resource_id
            if not resource_id:
                receipt["status"] = "no_verified_resource"
                return receipt
            try:
                current = api.request("GET", "/deployments/" + resource_id, timeout=5)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                receipt["status"] = "deleted"
                return receipt
            verify_owned(current, plan, resource_id)
            save(destination / "cleanup-identity.json", current)
            response = api.request("DELETE", "/deployments/" + resource_id, timeout=5)
            if response.get("id") != resource_id:
                raise RuntimeError(
                    "Deletion response identifies a different deployment"
                )
            receipt.update(status="deletion_requested", response=response)
            for _ in range(5):
                time.sleep(3)
                try:
                    current = api.request(
                        "GET", "/deployments/" + resource_id, timeout=5
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        receipt["status"] = "deleted"
                        break
                    raise
                if (
                    current.get("id") == resource_id
                    and deployment_state(current) == "deleted"
                ):
                    receipt["status"] = "deleted"
                    break
        except Exception as exc:
            receipt["error"] = str(redact(str(exc)))[:1000]
        finally:
            api.close()
            receipt["checked_at"] = now()
            save(destination / "cleanup.json", receipt)
        return receipt


def watchdog(directory: Path) -> dict[str, Any]:
    destination = directory / "training/deployment"
    started = json.loads((destination / "creation-started.json").read_text())
    while time.time() < started["deadline_unix"] - CLEANUP_RESERVE:
        path = destination / "cleanup.json"
        if path.exists() and json.loads(path.read_text()).get("status") == "deleted":
            return json.loads(path.read_text())
        time.sleep(
            min(15, max(0.1, started["deadline_unix"] - CLEANUP_RESERVE - time.time()))
        )
    return cleanup(directory)


def evaluate(
    api: Client, directory: Path, alias: str, deadline: float
) -> dict[str, Any]:
    destination = directory / "training/deployment"
    contract = json.loads((directory / "contract.json").read_text())
    deployed = json.loads((STATE / "sql-deployment.json").read_text())
    source = Path(deployed["path"]).read_text()
    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        sha(source) != manifest["executor_sha256"]
        or sha(Path(sql_benchmark.__file__).read_bytes())
        != manifest["benchmark_sha256"]
    ):
        raise RuntimeError("Frozen benchmark or accepted executor changed")
    public = sql_benchmark.public_tasks("heldout", contract["seed"])
    answers: dict[str, Any] = {}
    calls = []
    for question in public["questions"]:
        remaining = deadline - time.time() - CLEANUP_RESERVE
        if remaining < 30:
            raise TimeoutError(
                "Deployment lifetime leaves insufficient time for another question"
            )
        messages = [
            {"role": "system", "content": training.SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"schema": public["schema"], "question": question["question"]},
                    ensure_ascii=False,
                ),
            },
        ]
        response = api.http.post(
            INFERENCE,
            json={
                "model": alias,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 2000,
            },
            timeout=min(60, remaining),
        )
        response.raise_for_status()
        value = response.json()
        content = value["choices"][0]["message"].get("content", "").strip()
        if content.startswith(("```json", "```\n")):
            content = "\n".join(content.splitlines()[1:-1])
        try:
            answer = json.loads(content)
        except ValueError:
            answer = {"invalid_response": True}
        answers[question["id"]] = answer
        calls.append(
            {
                "question_id": question["id"],
                "response_id": value.get("id"),
                "model": value.get("model"),
                "usage": value.get("usage"),
                "output": content,
            }
        )
        save(destination / "inference.json", redact(calls))
        save(destination / "answers.json", answers)
    if deadline - time.time() < CLEANUP_RESERVE + 30:
        raise TimeoutError(
            "Deployment lifetime leaves insufficient time for isolated evaluation"
        )
    report = sql_benchmark.evaluate(answers, "heldout", contract["seed"], source)
    report.update(
        base_student_comparison="not_run", improvement_claim=False, promoted=False
    )
    save(destination / "evaluation.json", report)
    return report


def execute(directory: Path, seconds: int, approved_hash: str) -> dict[str, Any]:
    validate_budget(seconds)
    destination = directory / "training/deployment"
    plan = json.loads((destination / "recipe.json").read_text())
    unsigned = {key: value for key, value in plan.items() if key != "recipe_sha256"}
    if (
        plan.get("recipe_sha256") != approved_hash
        or digest(unsigned) != approved_hash
        or plan.get("max_seconds") != seconds
    ):
        raise ValueError("Execution does not match the approved recipe and lifetime")
    if plan.get("status") != "ready_for_approval":
        raise RuntimeError("The training checkpoint is not ready")
    with (destination / "execution.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (destination / "creation-started.json").exists():
            raise RuntimeError(
                "This recipe has already attempted creation; inspect receipts and cleanup before another run"
            )
        api = Client()
        receipt: dict[str, Any] = {"started_at": now(), "status": "failed"}
        try:
            with training.client() as trainer:
                job = trainer.fine_tuning.jobs.retrieve(plan["job"]["id"]).model_dump(
                    mode="json"
                )
            if (
                digest(job_binding(job)) != plan["job_binding_sha256"]
                or job.get("status") != "succeeded"
            ):
                raise RuntimeError(
                    "The provider checkpoint differs from the approved recipe"
                )
            flavor = selected_flavor(api.request("GET", "/flavors")["flavors"])
            if Decimal(str(flavor["price_per_hour"])) > Decimal(
                plan["hourly_cost_usd"]
            ):
                raise RuntimeError("Deployment price increased after preparation")
            before = api.request("GET", "/deployments")["deployments"]
            if any(
                item.get("deployment_name") == plan["request"]["deployment_name"]
                for item in before
            ):
                raise RuntimeError("The requested deployment alias already exists")
            deadline = time.time() + seconds
            save(
                destination / "creation-started.json",
                {
                    "started_at": now(),
                    "deadline_unix": deadline,
                    "recipe_sha256": approved_hash,
                    "prior_ids": [item["id"] for item in before],
                },
            )
            with (destination / "watchdog.log").open("w") as log:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "aya_factory.checkpoint",
                        directory.name,
                        "--watchdog",
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            save(
                destination / "watchdog.json",
                {"pid": child.pid, "deadline_unix": deadline},
            )
            created = api.request("POST", "/deployments", plan["request"])
            if not isinstance(created.get("id"), str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,120}", created["id"]
            ):
                raise RuntimeError("Create response omitted a valid deployment ID")
            save(destination / "created.json", created)
            while time.time() < deadline - CLEANUP_RESERVE:
                current = api.request("GET", "/deployments/" + created["id"])
                verify_owned(current, plan, created["id"])
                save(destination / "status.json", current)
                status = deployment_state(current)
                if status == "ready" and current.get("available_replicas") == 1:
                    receipt["evaluation"] = evaluate(
                        api, directory, plan["request"]["deployment_name"], deadline
                    )
                    receipt["status"] = "evaluated"
                    break
                if status in {"failed", "deleting", "deleted"}:
                    raise RuntimeError("Deployment entered " + status)
                time.sleep(min(10, max(0.1, deadline - CLEANUP_RESERVE - time.time())))
            else:
                raise TimeoutError(
                    "Deployment did not become ready within its approved lifetime"
                )
        except (Exception, KeyboardInterrupt) as exc:
            receipt["error"] = str(redact(str(exc)))[:1000]
        finally:
            api.close()
            if (destination / "creation-started.json").exists():
                receipt["cleanup"] = cleanup(directory)
            receipt["completed_at"] = now()
            save(destination / "receipt.json", receipt)
        return receipt


def interrupted(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt("Deployment execution interrupted; cleanup requested")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-seconds", type=int)
    parser.add_argument("--recipe-sha256")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--watchdog", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = directory_for(args.run_id)
    if sum((args.execute, args.cleanup, args.watchdog)) > 1:
        parser.error("Choose one operation")
    if args.execute and (args.max_seconds is None or not args.recipe_sha256):
        parser.error(
            "--execute requires --max-seconds and the approved --recipe-sha256"
        )
    signal.signal(signal.SIGTERM, interrupted)
    if args.execute:
        result = execute(directory, args.max_seconds, args.recipe_sha256)
    elif args.cleanup:
        result = cleanup(directory)
    elif args.watchdog:
        result = watchdog(directory)
    else:
        result = prepare(directory, args.max_seconds or 2700)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
