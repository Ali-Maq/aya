"""Rank owned development trajectories using independent scores and API readback.

Adapters support the frozen AYA SQL and public Spider experiments. Selection
never changes a trace, submits training, or uses held-out outcomes.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from . import sql_benchmark, telemetry
from .core import STATE, now, save, sha

Reader = Callable[[str], dict[str, Any]]
DEVELOPMENT = {"dev", "development"}
PRIVATE_KEYS = {
    "reasoning",
    "chain_of_thought",
    "private_reasoning",
    "thinking",
    "expected_sql",
    "gold_sql",
    "heldout",
    "held_out",
    "holdout",
}


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path.name}")
    return value


def digest(value: Any) -> str:
    return sha(json.dumps(value, sort_keys=True, allow_nan=False))


def json_value(value: Any) -> Any:
    """Langfuse can return a JSON text field as its parsed value."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def assert_public(value: Any) -> None:
    if isinstance(value, dict):
        if PRIVATE_KEYS.intersection(value):
            raise ValueError("Private reasoning is not an eligible trajectory")
        if value.get("reconstructed") or value.get("private") is True:
            raise ValueError("Private or reconstructed records are excluded")
        if str(value.get("split", "")).lower() in telemetry.NON_TRAINING_SPLITS:
            raise ValueError("Evaluation-only content is not eligible")
        if "reconstructed" in str(value.get("input_kind", "")).lower():
            raise ValueError("Reconstructed prompts are excluded")
        for item in value.values():
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)
    elif isinstance(value, str):
        parsed = json_value(value)
        if isinstance(parsed, (dict, list)):
            assert_public(parsed)


def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("Measured counts must be nonnegative integers")
    return value


def validate_report(report: dict[str, Any], public: dict[str, Any]) -> None:
    questions = public["questions"]
    identifiers = [row["id"] for row in questions]
    rows = report.get("by_question", [])
    is_public = report.get("benchmark") == "public-sql"
    variants = 1 if is_public else len(report.get("dataset_seeds", []))
    if (
        report.get("split") != "development"
        or report.get("protocol_valid") is not True
        or not identifiers
        or len(identifiers) != len(set(identifiers))
        or any(
            not str(key).startswith("spider-dev-" if is_public else "dev-")
            for key in identifiers
        )
        or len(rows) != len(identifiers)
        or {row["id"] for row in rows} != set(identifiers)
        or variants < 1
    ):
        raise ValueError(
            "Invalid development question identities or evaluation protocol"
        )
    for row in rows:
        passed, total = integer(row["passed"]), integer(row["total"], 1)
        if passed > total or total != variants:
            raise ValueError("Invalid independent check counts")
    if (
        integer(report.get("passed")) != sum(row["passed"] for row in rows)
        or integer(report.get("total"), 1) != sum(row["total"] for row in rows)
        or integer(report.get("task_total"), 1) != len(rows)
        or integer(report.get("task_passed"))
        != sum(row["passed"] == row["total"] for row in rows)
    ):
        raise ValueError("Independent score totals do not match question checks")


def workflow_path(directory: Path, episode: str) -> Path:
    if episode == "baseline":
        return directory / "task.txt"
    if episode == "v0":
        return directory / "initial-workflow.txt"
    if episode == "v1":
        proposal = read(directory / "rhi-propose-v0.json")
        path = Path(proposal["workflow_path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Workflow file is outside its owned experiment")
        if sha(path.read_bytes()) != proposal.get("workflow_sha256"):
            raise ValueError("Proposed workflow digest changed")
        return path
    raise ValueError("Only completed development episodes can be ranked")


def benchmark_context(report: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    """Validate the pinned dataset without reading held-out questions or gold outputs."""
    if report.get("benchmark") == "public-sql":
        from . import public_sql_benchmark

        catalog = public_sql_benchmark.catalog()
        specification = read(public_sql_benchmark.MANIFEST_PATH)
        validation_ids = specification.get("validation_ids", [])
        training_ids = specification.get("training_ids", [])
        development_ids = {row["id"] for row in specification["splits"]["development"]}
        if (
            not catalog["ready"]
            or not validation_ids
            or len(validation_ids) != len(set(validation_ids))
            or not set(validation_ids) < development_ids
            or len(training_ids) != len(set(training_ids))
            or set(training_ids) & set(validation_ids)
            or set(training_ids) | set(validation_ids) != development_ids
        ):
            raise ValueError(
                "A frozen public dataset and declared development validation IDs are required"
            )
        expected = {
            "dataset_sha256": catalog["dataset_source_sha256"],
            "dataset_source_sha256": catalog["dataset_source_sha256"],
            "case_sha256": catalog["case_manifest_sha256"],
            "case_manifest_sha256": catalog["case_manifest_sha256"],
            "executor_source_sha256": catalog["executor_sha256"],
            "evaluator_sha256": catalog["evaluator_sha256"],
        }
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError(
                "Public report differs from its pinned source, cases, executor, or evaluator"
            )
        if public != public_sql_benchmark.public_tasks("development"):
            raise ValueError(
                "Public episode input differs from the pinned development questions"
            )
        return {
            "evaluator_hash": catalog["evaluator_sha256"],
            "validation_ids": validation_ids,
            "schemas": {
                q["id"]: public["databases"][q["db_id"]]["schema"]
                for q in public["questions"]
            },
        }
    if report.get("benchmark") != "aya-nl-sql-v1":
        raise ValueError("Unsupported frozen evaluation profile")
    expected_data = [sql_benchmark.dataset(seed) for seed in report["dataset_seeds"]]
    if (
        public != sql_benchmark.public_tasks("development", report["seed"])
        or report["dataset_seeds"]
        != [report["seed"] + offset for offset in sql_benchmark.SEED_OFFSETS]
        or report["dataset_sha256"] != digest(expected_data)
        or report["case_sha256"] != digest(sql_benchmark.cases("development"))
    ):
        raise ValueError("Independent report dataset or question digest is invalid")
    return {
        "evaluator_hash": sha(Path(sql_benchmark.__file__).read_bytes()),
        "validation_ids": ["dev-license-groups", "dev-share"],
        "schemas": {q["id"]: public["schema"] for q in public["questions"]},
    }


def measured_usage(
    episode: Path, label: str, stored: dict[str, Any], revision: str
) -> dict[str, Any]:
    usage = read(episode / "usage.json")
    observations = [
        row
        for row in stored.get("observations", [])
        if row.get("metadata", {}).get("trajectory_revision") == revision
    ]
    if label == "baseline":
        provider = read(episode / "crusoe.json")
        generations = [row for row in observations if row.get("type") == "GENERATION"]
        if len(generations) != 1:
            raise ValueError("The baseline must have one captured provider generation")
        generation = generations[0]
        if (
            generation.get("metadata", {}).get("response_id")
            != provider.get("response_id")
            or not provider.get("response_id")
            or generation.get("metadata", {}).get("input_kind") != "captured_prompt"
            or json_value(generation.get("output"))
            != json_value(provider.get("content"))
        ):
            raise ValueError("The baseline provider receipt does not match Langfuse")
        tokens = provider["usage"]
        inputs, outputs = (
            integer(tokens["prompt_tokens"]),
            integer(tokens["completion_tokens"]),
        )
        calls = 1
        if generation.get("usageDetails", {}).get("total") != inputs + outputs:
            raise ValueError("Provider token usage differs from Langfuse")
        if (
            usage.get("prompt_tokens") != inputs
            or usage.get("completion_tokens") != outputs
        ):
            raise ValueError(
                "Baseline usage receipt differs from its provider response"
            )
    else:
        audit = read(episode / f"{label}-audit.json")
        sessions = [
            row["metadata"]
            for row in observations
            if row.get("type") == "SPAN"
            and row.get("name", "").startswith("Hermes session ")
        ]
        if not sessions or {s["id"] for s in sessions} != {
            s["id"] for s in audit["sessions"]
        }:
            raise ValueError("Native session identities differ from their audit")
        calls = sum(integer(s["api_call_count"]) for s in sessions)
        inputs = sum(integer(s["input_tokens"]) for s in sessions)
        outputs = sum(integer(s["output_tokens"]) for s in sessions)
        for key, value in (
            ("api_calls", calls),
            ("input_tokens", inputs),
            ("output_tokens", outputs),
        ):
            if audit.get(key) != value or usage.get(key) != value:
                raise ValueError(
                    "Native usage differs from the recorded Langfuse sessions"
                )
    elapsed = usage.get("elapsed_seconds")
    if (
        usage.get("api_calls") != calls
        or calls < 1
        or type(elapsed) not in {int, float}
        or not math.isfinite(elapsed)
        or elapsed <= 0
    ):
        raise ValueError("Missing or invalid measured episode usage")
    return {
        "api_calls": calls,
        "input_tokens": inputs,
        "output_tokens": outputs,
        "total_tokens": inputs + outputs,
        "elapsed_seconds": elapsed,
        "scope": "whole episode; no per-question cost allocation",
        "price_usd": None,
    }


def candidate(
    directory: Path, label: str, fetch: Reader, *, state_root: Path = STATE
) -> dict[str, Any]:
    episode = directory / f"{directory.name}-{label}"
    status = read(episode / "run_status.json")
    if status.get("status") != "completed" or status.get("split") not in DEVELOPMENT:
        raise ValueError("Failed, incomplete, or held-out episodes are excluded")
    canonical = state_root / "telemetry" / episode.name
    receipt = read(canonical / "receipt.json")
    payload = read(canonical / "trajectory.json")
    metadata = payload.get("metadata", {})
    if (
        metadata.get("split") not in DEVELOPMENT
        or metadata.get("eligible_for_training") is not True
    ):
        raise ValueError("Trajectory is not explicitly eligible development data")
    assert_public(payload)
    revision = telemetry.payload_hash(payload)
    if (
        receipt.get("status") != "verified"
        or receipt.get("trajectory_revision") != revision
    ):
        raise ValueError("A verified current Langfuse receipt is required")
    trace_id = telemetry.identity(episode.name, "trace")
    if receipt.get("trace_id") != trace_id:
        raise ValueError("Trace identity differs from the owned episode")
    report = read(episode / "results.json")
    public = read(episode / "public-tasks.json")
    answers = read(episode / "queries.json")
    manifest, contract = (
        read(directory / "manifest.json"),
        read(directory / "contract.json"),
    )
    frozen = read(directory / "rhi-input-manifest.json")["sha256"]
    context = benchmark_context(report, public)
    evaluator_hash = context["evaluator_hash"]
    bindings = {
        "task_file": sha((directory / "task.txt").read_bytes()),
        "contract": sha((directory / "contract.json").read_bytes()),
        "dataset": sha((directory / "dataset.json").read_bytes()),
        "evaluator": evaluator_hash,
    }
    if frozen != bindings or manifest.get("benchmark_sha256") != evaluator_hash:
        raise ValueError("Frozen task, contract, dataset, or evaluator has changed")
    if (
        report.get("executor_source_sha256") != manifest.get("executor_sha256")
        or report.get("executor_source_sha256")
        != contract.get("executor_source_sha256")
        or public != read(directory / "dataset.json")
        or metadata.get("contract_hash") != bindings["task_file"]
        or metadata.get("dataset_hash") != report.get("dataset_sha256")
        or metadata.get("version_hash")
        != sha(workflow_path(directory, label).read_bytes())
    ):
        raise ValueError("Task, dataset, executor, or workflow binding does not match")
    validate_report(report, public)
    view = (
        directory
        / "rhi-views"
        / (
            "reference/query1001"
            if label == "baseline"
            else f"{label}/query1001_ourTeam"
        )
    )
    snapshot = read(view / "snapshot.json")
    if snapshot.get("split") != "development" or any(
        snapshot.get("files", {}).get(name) != sha((episode / name).read_bytes())
        for name in ("queries.json", "results.json", "run_status.json")
    ):
        raise ValueError(
            "Independent report or answers differ from their frozen evaluation snapshot"
        )
    if set(answers) != {row["id"] for row in public["questions"]}:
        raise ValueError("Answer identities differ from the evaluated questions")
    for answer in answers.values():
        if not (
            isinstance(answer, dict)
            and (
                (set(answer) == {"sql"} and isinstance(answer["sql"], str))
                or (set(answer) == {"refused"} and answer["refused"] is True)
            )
        ):
            raise ValueError("Only final SQL answers or refusals can be exported")
    if payload.get("input") != public or payload.get("output") != answers:
        raise ValueError("Local telemetry differs from the evaluated episode")
    stored = fetch(trace_id)
    assert_public(stored)
    actual_meta = stored.get("metadata", {})
    if (
        stored.get("id") != trace_id
        or actual_meta.get("trajectory_revision") != revision
        or actual_meta.get("run_id") != episode.name
        or actual_meta.get("split") not in DEVELOPMENT
        or actual_meta.get("eligible_for_training") is not True
        or any(
            actual_meta.get(key) != metadata.get(key)
            for key in ("dataset_hash", "contract_hash", "version_hash")
        )
        or stored.get("input") != public
        or stored.get("output") != answers
    ):
        raise ValueError(
            "Live Langfuse readback differs from the evaluated eligible episode"
        )
    events = telemetry.make_events(episode.name, payload)
    wanted = {
        row["body"]["id"]
        for row in events
        if row["type"] not in {"trace-create", "score-create"}
    }
    observations = [
        row
        for row in stored.get("observations", [])
        if row.get("metadata", {}).get("trajectory_revision") == revision
    ]
    if not wanted <= {row["id"] for row in observations}:
        raise ValueError(
            "Live Langfuse action or generation observations are incomplete"
        )
    actual_observations = {row["id"]: row for row in observations}
    for event in events:
        body = event["body"]
        if body["id"] not in wanted:
            continue
        for field in ("input", "output"):
            if field in body and json_value(body[field]) != json_value(
                actual_observations[body["id"]].get(field)
            ):
                raise ValueError(
                    "Recorded action or prompt content differs from live Langfuse"
                )
    usage = measured_usage(episode, label, stored, revision)
    comparable = {
        **bindings,
        "dataset_sha256": report["dataset_sha256"],
        "case_sha256": report["case_sha256"],
        "executor_source_sha256": report["executor_source_sha256"],
        "validation_assignment_sha256": digest(context["validation_ids"]),
    }
    pointer = read(episode / "telemetry.json")
    comparison = directory / "rhi-compare-v1.json"
    retained = read(comparison).get("retained", {}) if comparison.exists() else {}
    retained_by_mass = (
        label in {"v0", "v1"}
        and retained.get("beats_reference") is True
        and type(retained.get("version")) is int
        and retained["version"] == int(label[1:])
    )
    return {
        "run_id": episode.name,
        "experiment_id": directory.name,
        "episode": label,
        "benchmark": report["benchmark"],
        "status": "verified",
        "trace_id": trace_id,
        "trace_url": receipt["trace_url"],
        "trajectory_revision": revision,
        "workflow_sha256": metadata["version_hash"],
        "comparable": comparable,
        "group_id": digest(comparable),
        "report_sha256": sha((episode / "results.json").read_bytes()),
        "answers_sha256": sha((episode / "queries.json").read_bytes()),
        "passed": report["passed"],
        "total": report["total"],
        "by_question": report["by_question"],
        "usage": usage,
        "input": stored["input"],
        "output": stored["output"],
        "retained_by_mass": retained_by_mass,
        "validation_ids": context["validation_ids"],
        "schemas": context["schemas"],
        "provenance": {
            "source": "Langfuse API readback",
            "verified_at": now(),
            "observation_ids": sorted(wanted),
            "readback_sha256": digest(stored),
            "score_authority": "host independent frozen SQL evaluator report",
        },
        "notes": (
            [
                "Episode telemetry pointer is stale; current canonical receipt and API revision were verified"
            ]
            if pointer.get("trajectory_revision") != revision
            else []
        ),
    }


def rank(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in candidates:
        for score in item["by_question"]:
            groups.setdefault((item["group_id"], score["id"]), []).append(
                {"candidate": item, "passed": score["passed"], "total": score["total"]}
            )
    tasks, exports = [], []
    selected_counts: Counter[str] = Counter()
    for (group_id, question_id), rows in sorted(groups.items()):
        rows.sort(
            key=lambda row: (
                -Fraction(row["passed"], row["total"]),
                row["candidate"]["usage"]["api_calls"],
                row["candidate"]["usage"]["total_tokens"],
                row["candidate"]["usage"]["elapsed_seconds"],
                row["candidate"]["run_id"],
            )
        )
        winner = rows[0]["candidate"] if rows[0]["passed"] == rows[0]["total"] else None
        tasks.append(
            {
                "group_id": group_id,
                "question_id": question_id,
                "selected_run_id": winner["run_id"] if winner else None,
                "reason": (
                    "All checks passed; then lowest measured episode calls, tokens, and latency"
                    if winner
                    else "No candidate passed every independent check"
                ),
                "ranked": [
                    {
                        "rank": i + 1,
                        "run_id": row["candidate"]["run_id"],
                        "passed": row["passed"],
                        "total": row["total"],
                        "eligible_for_export": row["passed"] == row["total"],
                        "usage": row["candidate"]["usage"],
                    }
                    for i, row in enumerate(rows)
                ],
            }
        )
        if winner:
            selected_counts[winner["run_id"]] += 1
            task = next(
                t for t in winner["input"]["questions"] if t["id"] == question_id
            )
            exports.append(
                {
                    "question_id": question_id,
                    "group_id": group_id,
                    "schema": winner["schemas"][question_id],
                    "question": task["question"],
                    "answer": winner["output"][question_id],
                    "source_run_id": winner["run_id"],
                    "trace_id": winner["trace_id"],
                    "trace_url": winner["trace_url"],
                    "trajectory_revision": winner["trajectory_revision"],
                    "workflow_sha256": winner["workflow_sha256"],
                    "bindings": winner["comparable"],
                    "report_sha256": winner["report_sha256"],
                    "provenance": winner["provenance"],
                    "mode": "final-answer SFT distillation",
                    "split": "development",
                    "assignment": "validation"
                    if question_id in winner["validation_ids"]
                    else "training",
                }
            )
    return {
        "tasks": tasks,
        "exports": exports,
        "selected_counts": dict(selected_counts),
    }


def select(
    directories: list[Path], *, state_root: Path = STATE, fetch: Reader | None = None
) -> dict[str, Any]:
    """Write an immutable selection manifest; perform GET requests only."""
    if fetch is None:
        settings = telemetry.config()

        def fetch(identity: str) -> dict[str, Any]:
            result = telemetry.request(settings, "/api/public/traces/" + identity)
            if result.get("projectId") != settings.project_id:
                raise ValueError(
                    "Langfuse project identity differs from the configured project"
                )
            return result

    candidates, excluded = [], []
    for directory in directories:
        if not re.fullmatch(r"[a-f0-9]{16}", directory.name):
            raise ValueError("Invalid owned MASS experiment identity")
        for path in sorted(directory.glob(directory.name + "-*")):
            if not path.is_dir() or not (path / "run_status.json").exists():
                continue
            label = path.name[len(directory.name) + 1 :]
            try:
                candidates.append(
                    candidate(directory, label, fetch, state_root=state_root)
                )
            except (ValueError, KeyError, OSError, TypeError) as exc:
                reason = (
                    "Missing required evidence: " + Path(exc.filename).name
                    if isinstance(exc, FileNotFoundError) and exc.filename
                    else str(telemetry.clean(str(exc))).replace(
                        str(state_root), "[private state]"
                    )
                )
                excluded.append({"run_id": path.name, "reason": reason})
    result = rank(candidates)
    summaries = [
        {
            key: value
            for key, value in item.items()
            if key not in {"input", "output", "by_question", "schemas"}
        }
        for item in candidates
    ]
    for item in summaries:
        baseline = next(
            (
                other
                for other in candidates
                if other["experiment_id"] == item["experiment_id"]
                and other["episode"] == "baseline"
                and other["group_id"] == item["group_id"]
            ),
            None,
        )
        item["mass_winning_teacher_eligible"] = bool(
            baseline
            and item["retained_by_mass"]
            and item["episode"] != "baseline"
            and item["passed"] > baseline["passed"]
        )
        item["mass_eligibility_reason"] = (
            "Independently beats the comparable bare reference and upstream MASS retained this workflow"
            if item["mass_winning_teacher_eligible"]
            else "Requires both independent improvement over the bare reference and upstream MASS retention"
        )
    manifest = {
        "schema": "aya-trajectory-selection-v1",
        "status": "ready",
        "created_at": now(),
        "mode": "final-answer SFT distillation; no job submitted",
        "heldout_rows": 0,
        "criterion": "Independent question pass rate, then measured episode API calls, tokens, latency, stable run ID",
        "cost_scope": "Episode totals are reused only as tie-breakers; they are never added across selected questions",
        "limitations": "Frozen AYA SQL or public Spider development tasks; no generalization or model-improvement claim. No dollar price inferred.",
        "candidates": summaries,
        "excluded": excluded,
        "tasks": result["tasks"],
        "selected_counts": result["selected_counts"],
        "selected_rows": len(result["exports"]),
        "assignments": dict(Counter(row["assignment"] for row in result["exports"])),
        "selected_sha256": digest({"rows": result["exports"]}),
    }
    fingerprint = digest(manifest)
    destination = state_root / "trajectory-selection" / fingerprint[:16]
    save(destination / "manifest.json", manifest)
    save(
        destination / "selected.json",
        {"rows": result["exports"], "manifest_sha256": fingerprint},
    )
    save(state_root / "trajectory-selection" / "report.json", manifest)
    return {
        **manifest,
        "manifest_sha256": fingerprint,
        "manifest_path": str(destination / "manifest.json"),
        "export_path": str(destination / "selected.json"),
    }


def load_verified_export(
    manifest_path: Path, *, state_root: Path = STATE, fetch: Reader | None = None
) -> dict[str, Any]:
    """Verify immutable export digests and refresh every source through Langfuse GET."""
    manifest = read(manifest_path)
    selected = read(manifest_path.parent / "selected.json")
    rows = selected.get("rows", [])
    if (
        selected.get("manifest_sha256") != digest(manifest)
        or manifest.get("selected_sha256") != digest({"rows": rows})
        or manifest.get("heldout_rows") != 0
    ):
        raise ValueError("Selection manifest or selected-answer digest changed")
    if fetch is None:
        settings = telemetry.config()

        def fetch(identity: str) -> dict[str, Any]:
            result = telemetry.request(settings, "/api/public/traces/" + identity)
            if result.get("projectId") != settings.project_id:
                raise ValueError("Langfuse project identity changed")
            return result

    sources: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        source = row["source_run_id"]
        if not re.fullmatch(r"[a-f0-9]{16}-(baseline|v0|v1)", source):
            raise ValueError("Invalid selection source identity")
        identity, label = source.rsplit("-", 1)
        if source not in sources:
            sources[source] = candidate(
                state_root / "mass" / identity, label, fetch, state_root=state_root
            )
        current = sources[source]
        key = (row["group_id"], row["question_id"])
        questions = {task["id"]: task for task in current["input"]["questions"]}
        task = questions.get(row["question_id"], {})
        score = next(
            (s for s in current["by_question"] if s["id"] == row["question_id"]), {}
        )
        expected_assignment = (
            "validation"
            if row["question_id"] in current["validation_ids"]
            else "training"
        )
        if (
            key in seen
            or row.get("split") != "development"
            or row.get("assignment") != expected_assignment
            or row.get("group_id") != current["group_id"]
            or row.get("bindings") != current["comparable"]
            or row.get("question") != task.get("question")
            or row.get("schema") != current["schemas"][row["question_id"]]
            or row.get("answer") != current["output"].get(row["question_id"])
            or not score
            or score["passed"] != score["total"]
            or any(
                row.get(field) != current.get(field)
                for field in (
                    "trace_id",
                    "trajectory_revision",
                    "workflow_sha256",
                    "report_sha256",
                )
            )
        ):
            raise ValueError(
                "Selected answer no longer matches its independently verified source"
            )
        seen.add(key)
    return {
        "manifest": manifest,
        "rows": rows,
        "verified_at": now(),
        "sources": [
            {
                "run_id": c["run_id"],
                "trace_id": c["trace_id"],
                "trajectory_revision": c["trajectory_revision"],
            }
            for c in sources.values()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="*")
    arguments = parser.parse_args()
    directories = (
        [STATE / "mass" / identity for identity in arguments.run_ids]
        if arguments.run_ids
        else sorted((STATE / "mass").glob("*"))
    )
    result = select(directories)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "selected_counts",
                    "selected_rows",
                    "excluded",
                    "manifest_path",
                    "export_path",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
