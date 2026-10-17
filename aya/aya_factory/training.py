"""Crusoe supervised LoRA training from verified Langfuse development records."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
from openai import APIStatusError, OpenAI

from . import sql_runtime, telemetry
from .core import Journal, now, save, sha

BASE = "https://api.intelligence.crusoecloud.com/v1"
STUDENT = "Qwen/Qwen3.5-9B"
SYSTEM = (
    "Translate a question into one read-only SQLite SELECT over the supplied schema. "
    'Return only JSON: {"sql":"..."} or {"refused":true}. Refuse writes, external files, '
    "extra databases and extensions. Preserve requested column order, ordering, ties and NULL semantics. "
    "Generalize to all records with this schema. Never return a literal snapshot answer."
)
VALIDATION_IDS = {"dev-license-groups", "dev-share"}


def client() -> OpenAI:
    return OpenAI(
        api_key=sql_runtime.key(),
        base_url=BASE,
        max_retries=0,
        timeout=60,
        default_headers={"User-Agent": "AYA-MASS/0.1"},
        http_client=httpx.Client(trust_env=False),
    )


def prepare(directory: Path, selected: Path) -> dict[str, Any]:
    importlib.reload(telemetry)
    receipt = json.loads((selected / "telemetry.json").read_text())
    if receipt.get("status") != "verified":
        raise RuntimeError("Training requires verified Langfuse API readback")
    if not receipt.get("training_export"):
        # Recover only an already verified record with an explicitly eligible development split.
        original = Path(receipt["receipt_path"]).parent / "trajectory.json"
        payload = json.loads(original.read_text())
        metadata = payload.get("metadata", {})
        if (
            metadata.get("split") not in {"dev", "development"}
            or metadata.get("eligible_for_training") is not True
        ):
            raise RuntimeError("This trajectory is not training eligible")
        metadata["split"] = "dev"
        metadata["framework"] = "MASS"
        payload["workflow"] = (directory / "selected-workflow.txt").read_text()
        receipt = telemetry.record_run(selected.name, payload)
        save(selected / "telemetry.json", receipt)
    if receipt.get("status") != "verified" or not receipt.get("training_export"):
        raise RuntimeError(
            "Langfuse did not release an eligible development trajectory"
        )
    trajectory = json.loads(Path(receipt["training_export"]).read_text())
    report = json.loads((selected / "results.json").read_text())
    answers = json.loads((selected / "queries.json").read_text())
    metadata = trajectory.get("metadata", {})
    provenance = trajectory.get("provenance", {})
    if (
        metadata.get("split") not in {"dev", "development"}
        or metadata.get("eligible_for_training") is not True
    ):
        raise RuntimeError("This Langfuse export is not eligible development data")
    if (
        provenance.get("source") != "Langfuse API readback"
        or provenance.get("trace_id") != receipt.get("trace_id")
        or not receipt.get("trajectory_revision")
        or provenance.get("trajectory_revision") != receipt["trajectory_revision"]
        or metadata.get("trajectory_revision") != receipt["trajectory_revision"]
    ):
        raise RuntimeError(
            "The training export does not match the verified Langfuse revision"
        )
    if (
        metadata.get("dataset_hash") != report.get("dataset_sha256")
        or metadata.get("version_hash")
        != sha((directory / "selected-workflow.txt").read_bytes())
        or metadata.get("contract_hash") != sha((directory / "task.txt").read_bytes())
    ):
        raise RuntimeError(
            "Training dataset, workflow, or contract hash differs from the verified episode"
        )
    if trajectory["output"] != answers or report["split"] != "development":
        raise RuntimeError(
            "Training outputs differ from the independently evaluated development record"
        )
    public = trajectory["input"]
    if public != json.loads(
        (selected / "public-tasks.json").read_text()
    ) or public != json.loads((directory / "dataset.json").read_text()):
        raise RuntimeError("Training input differs from the evaluated episode")
    question_ids = [task["id"] for task in public["questions"]]
    rows = report["by_question"]
    variants = len(report.get("dataset_seeds", []))
    if (
        len(question_ids) != len(set(question_ids))
        or any(
            not isinstance(key, str) or not key.startswith("dev-")
            for key in question_ids
        )
        or set(answers) != set(question_ids)
        or len(rows) != len(question_ids)
        or {row["id"] for row in rows} != set(question_ids)
        or variants < 1
        or report.get("protocol_valid") is not True
        or any(
            type(row["passed"]) is not int
            or type(row["total"]) is not int
            or row["total"] != variants
            or not 0 <= row["passed"] <= variants
            for row in rows
        )
    ):
        raise RuntimeError(
            "Training question identities or independent score counts are invalid"
        )
    passed = {r["id"] for r in report["by_question"] if r["passed"] == r["total"]}
    train, validation, identifiers = [], [], {"training": [], "validation": []}
    for task in public["questions"]:
        if task["id"] not in passed:
            continue
        row = {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"schema": public["schema"], "question": task["question"]},
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(answers[task["id"]], ensure_ascii=False),
                },
            ]
        }
        target = "validation" if task["id"] in VALIDATION_IDS else "training"
        (validation if target == "validation" else train).append(row)
        identifiers[target].append(task["id"])
    if len(train) < 10 or len(validation) < 2:
        raise RuntimeError(
            "This bounded experiment needs ten passing training tasks and two passing validation tasks"
        )
    destination = directory / "training"
    destination.mkdir(exist_ok=True)
    for name, rows in (("training", train), ("validation", validation)):
        (destination / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        )
    manifest = {
        "format": "assistant-only supervised chat",
        "teacher": "deepseek-ai/DeepSeek-V4-Pro",
        "student": STUDENT,
        "kind": "distilled final SQL outputs from verified agent trajectories",
        "mode": "supervised integration smoke test",
        "mass_eligibility": "Not a MASS winning-teacher training round: no workflow beat the bare reference in this run",
        "training_rows": len(train),
        "validation_rows": len(validation),
        "question_ids": identifiers,
        "heldout_rows": 0,
        "langfuse_trace": receipt["trace_url"],
        "trajectory_revision": receipt["trajectory_revision"],
        "workflow_sha256": sha((directory / "selected-workflow.txt").read_bytes()),
        "files": {
            name: sha((destination / f"{name}.jsonl").read_bytes())
            for name in ("training", "validation")
        },
        "limitations": "Small integration smoke test; insufficient evidence of generalization or weight improvement",
    }
    save(destination / "manifest.json", manifest)
    return manifest


def prepare_and_submit(directory: Path, selected: Path) -> dict[str, Any]:
    if (directory / "training/job.json").exists():
        return refresh(directory)
    if (directory / "training/submission-started.json").exists():
        raise RuntimeError(
            "A prior training submission has an unknown outcome; inspect provider jobs before retrying"
        )
    manifest = prepare(directory, selected)
    return submit_prepared(directory, manifest)


def prepare_selection(directory: Path, manifest_path: Path) -> dict[str, Any]:
    """Build a new corpus only from reverified, independently passing answers."""
    from . import trajectory_selection

    destination = directory / "training"
    if any(
        (destination / filename).exists()
        for filename in (
            "submission-started.json",
            "job.json",
            "training-file.json",
            "validation-file.json",
        )
    ):
        raise RuntimeError("An existing training corpus cannot be replaced")
    verified = trajectory_selection.load_verified_export(manifest_path)
    selection, rows = verified["manifest"], verified["rows"]
    if not rows or len({row["group_id"] for row in rows}) != 1:
        raise ValueError("Training needs one comparable benchmark group")
    datasets: dict[str, list[dict[str, Any]]] = {"training": [], "validation": []}
    identifiers: dict[str, list[str]] = {"training": [], "validation": []}
    for row in rows:
        assignment = row["assignment"]
        datasets[assignment].append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"schema": row["schema"], "question": row["question"]},
                            ensure_ascii=False,
                        ),
                    },
                    {"role": "assistant", "content": json.dumps(row["answer"])},
                ]
            }
        )
        identifiers[assignment].append(row["question_id"])
    if set(identifiers["training"]) & set(identifiers["validation"]):
        raise ValueError("Training and validation questions overlap")
    destination.mkdir(parents=True, exist_ok=True)
    for name, records in datasets.items():
        (destination / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
        )
    selected_sources = set(selection["selected_counts"])
    winning_sources = {
        row["run_id"]
        for row in selection["candidates"]
        if row.get("mass_winning_teacher_eligible")
    }
    eligible = len(datasets["training"]) >= 10 and len(datasets["validation"]) >= 2
    manifest = {
        "format": "assistant-only supervised chat",
        "teacher": "deepseek-ai/DeepSeek-V4-Pro",
        "student": STUDENT,
        "kind": "distilled final SQL outputs from ranked verified trajectories",
        "mode": "supervised integration smoke test",
        "selection_sha256": trajectory_selection.digest(selection),
        "selection_rule": selection["criterion"],
        "source_runs": sorted(selected_sources),
        "source_readback": verified["sources"],
        "verified_at": verified["verified_at"],
        "training_rows": len(datasets["training"]),
        "validation_rows": len(datasets["validation"]),
        "question_ids": identifiers,
        "heldout_rows": 0,
        "submission_eligible": eligible,
        "submission_gate": "At least ten passing training tasks and two preassigned passing validation tasks",
        "mass_winning_teacher_sources": sorted(selected_sources & winning_sources),
        "mass_eligibility": (
            "All selected sources beat the bare reference and were retained by MASS"
            if selected_sources <= winning_sources
            else "Includes non-winning sources; final-answer distillation, not a MASS winning-teacher round"
        ),
        "workflow_sha256": sha(
            json.dumps(sorted({row["workflow_sha256"] for row in rows}))
        ),
        "files": {
            name: sha((destination / f"{name}.jsonl").read_bytes()) for name in datasets
        },
        "limitations": "Small final-answer corpus; no full tool-trajectory training or model-improvement claim",
    }
    save(destination / "selection.json", selection)
    save(destination / "manifest.json", manifest)
    return manifest


def submit_prepared(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    destination = directory / "training"
    journal = Journal(directory)
    request_path = directory / "github-request.json"
    if request_path.is_file():
        contract = json.loads(request_path.read_text())["contract"]
        if contract.get("benchmark") == "public-sql":
            gate = contract["training_export"]
            required = {
                "automatic_training_submission": True,
                "minimum_training_rows": 10,
                "minimum_validation_rows": 2,
                "epochs": 1,
                "student": STUDENT,
                "lora_rank": 16,
                "lora_alpha": 32,
            }
            if any(gate.get(key) != value for key, value in required.items()):
                raise RuntimeError(
                    "The frozen GitHub contract does not authorize this training recipe"
                )
            identifiers = manifest["question_ids"]
            if (
                len(identifiers["training"]) < gate["minimum_training_rows"]
                or len(identifiers["validation"]) < gate["minimum_validation_rows"]
                or not set(identifiers["training"]) <= set(gate["training_ids"])
                or not set(identifiers["validation"]) <= set(gate["validation_ids"])
            ):
                raise RuntimeError(
                    "The corpus does not meet the frozen GitHub training assignments"
                )
    if json.loads((destination / "manifest.json").read_text()) != manifest:
        raise RuntimeError("Training manifest differs from the saved corpus")
    if manifest.get("submission_eligible") is False:
        raise RuntimeError(
            "The verified corpus does not meet its frozen submission gate"
        )
    for name in ("training", "validation"):
        if sha((destination / f"{name}.jsonl").read_bytes()) != manifest["files"][name]:
            raise RuntimeError("Prepared training corpus changed before submission")
    if (destination / "job.json").exists():
        return refresh(directory)
    if (destination / "submission-started.json").exists():
        raise RuntimeError(
            "A prior training submission has an unknown outcome; inspect provider jobs before retrying"
        )
    with client() as api:
        models = api.get("/public/models", cast_to=dict[str, Any])
        save(destination / "models.json", models)
        chosen = next(
            (
                m
                for m in models["data"]
                if m.get("model_name") == STUDENT and m.get("fine_tuning_available")
            ),
            None,
        )
        if not chosen:
            raise RuntimeError("The selected student is unavailable for fine-tuning")
        files = {}
        for name in ("training", "validation"):
            receipt_path = destination / f"{name}-file.json"
            if receipt_path.exists():
                value = json.loads(receipt_path.read_text())
                if value.get("aya_source_sha256") != manifest["files"][name]:
                    raise RuntimeError(
                        "Uploaded training file differs from the prepared corpus"
                    )
            else:
                with (destination / f"{name}.jsonl").open("rb") as stream:
                    value = api.files.create(
                        file=stream, purpose="fine-tune"
                    ).model_dump(mode="json")
                value["aya_source_sha256"] = manifest["files"][name]
                save(receipt_path, value)
            files[name] = value["id"]
        body = {
            "model": chosen["id"],
            "training_file": files["training"],
            "validation_file": files["validation"],
            "suffix": "aya-sql-" + directory.name[-8:],
            "seed": 42,
            "method": {
                "type": "supervised",
                "supervised": {
                    "hyperparameters": {
                        "n_epochs": 1,
                        "batch_size": "auto",
                        "learning_rate": 0.0001,
                        "lora_rank": 16,
                        "lora_alpha": 32,
                    }
                },
            },
            "metadata": {
                "aya_run": directory.name,
                "workflow_sha256": manifest["workflow_sha256"],
            },
        }
        save(destination / "submission-started.json", {"at": now(), "request": body})
        try:
            job = api.fine_tuning.jobs.create(**body).model_dump(mode="json")
        except APIStatusError as exc:
            if exc.status_code in {400, 422}:
                rejected = {
                    "at": now(),
                    "request": body,
                    "status": exc.status_code,
                    "error": str(exc),
                }
                save(
                    destination / ("rejected-" + str(time.time_ns()) + ".json"),
                    rejected,
                )
                (destination / "submission-started.json").unlink()
                journal.emit(
                    "training_request_rejected", status=exc.status_code, error=str(exc)
                )
            raise
        save(destination / "job.json", job)
        journal.emit(
            "training_submitted",
            job_id=job["id"],
            model=chosen["model_name"],
            status=job["status"],
            training_rows=manifest["training_rows"],
            validation_rows=manifest["validation_rows"],
        )
    return refresh(directory)


def refresh(directory: Path) -> dict[str, Any]:
    destination = directory / "training"
    job = json.loads((destination / "job.json").read_text())
    with client() as api:
        current = api.fine_tuning.jobs.retrieve(job["id"]).model_dump(mode="json")
        save(destination / "job.json", current)
        timeline = api.fine_tuning.jobs.list_events(job["id"], limit=30).model_dump(
            mode="json"
        )
        save(destination / "events.json", timeline)
        if current["status"] == "succeeded":
            save(
                destination / "checkpoints.json",
                api.fine_tuning.jobs.checkpoints.list(job["id"]).model_dump(
                    mode="json"
                ),
            )
    receipt = {
        "id": current["id"],
        "status": current["status"],
        "model": STUDENT,
        "fine_tuned_model": current.get("fine_tuned_model"),
        "trained_tokens": current.get("trained_tokens"),
        "error": current.get("error"),
        "updated_at": now(),
        "url": "https://console.crusoecloud.com/foundry/fine-tuning/jobs/"
        + current["id"]
        + "/overview",
        "deployment_status": "required",
        "promotion": "blocked until tuned inference passes independent evaluation",
    }
    save(destination / "receipt.json", receipt)
    return receipt
