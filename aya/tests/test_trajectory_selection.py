"""Offline selection boundary tests; fixture scores are not experiment evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aya_factory import sql_benchmark, telemetry
from aya_factory import trajectory_selection as selection
from aya_factory.core import save, sha


class TrajectorySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.run = self.state / "mass" / "aaaaaaaaaaaaaaaa"
        self.run.mkdir(parents=True)
        (self.run / "task.txt").write_text("Fixture task")
        (self.run / "initial-workflow.txt").write_text("Fixture workflow")
        self.public = sql_benchmark.public_tasks("development", 42)
        self.answers = {q["id"]: {"sql": "SELECT 1"} for q in self.public["questions"]}
        seeds = [42 + offset for offset in sql_benchmark.SEED_OFFSETS]
        self.report = {
            "benchmark": "aya-nl-sql-v1",
            "split": "development",
            "seed": 42,
            "dataset_seeds": seeds,
            "dataset_sha256": selection.digest(
                [sql_benchmark.dataset(s) for s in seeds]
            ),
            "case_sha256": selection.digest(sql_benchmark.cases("development")),
            "executor_source_sha256": sha("fixture executor"),
            "passed": 36,
            "total": 36,
            "task_passed": 12,
            "task_total": 12,
            "protocol_valid": True,
            "by_question": [
                {"id": key, "passed": 3, "total": 3} for key in self.answers
            ],
        }
        save(self.run / "dataset.json", self.public)
        save(
            self.run / "contract.json",
            {"executor_source_sha256": sha("fixture executor")},
        )
        evaluator_hash = sha(Path(sql_benchmark.__file__).read_bytes())
        save(
            self.run / "manifest.json",
            {
                "benchmark_sha256": evaluator_hash,
                "executor_sha256": sha("fixture executor"),
            },
        )
        save(
            self.run / "rhi-input-manifest.json",
            {
                "sha256": {
                    "task_file": sha((self.run / "task.txt").read_bytes()),
                    "contract": sha((self.run / "contract.json").read_bytes()),
                    "dataset": sha((self.run / "dataset.json").read_bytes()),
                    "evaluator": evaluator_hash,
                }
            },
        )
        self.api: dict[str, dict[str, Any]] = {}
        self.add_episode("baseline", 1, 100, 20, 2.0)
        self.add_episode("v0", 8, 800, 200, 20.0)

    def add_episode(
        self, label: str, calls: int, inputs: int, outputs: int, elapsed: float
    ) -> None:
        episode = self.run / f"{self.run.name}-{label}"
        episode.mkdir()
        save(
            episode / "run_status.json", {"status": "completed", "split": "development"}
        )
        for filename, value in (
            ("public-tasks", self.public),
            ("queries", self.answers),
            ("results", self.report),
        ):
            save(episode / f"{filename}.json", value)
        view = (
            self.run
            / "rhi-views"
            / (
                "reference/query1001"
                if label == "baseline"
                else f"{label}/query1001_ourTeam"
            )
        )
        save(
            view / "snapshot.json",
            {
                "split": "development",
                "files": {
                    name: sha((episode / name).read_bytes())
                    for name in ("queries.json", "results.json", "run_status.json")
                },
            },
        )
        payload: dict[str, Any] = {
            "input": self.public,
            "output": self.answers,
            "metadata": {
                "split": "dev",
                "eligible_for_training": True,
                "version_hash": sha(
                    selection.workflow_path(self.run, label).read_bytes()
                ),
                "dataset_hash": self.report["dataset_sha256"],
                "contract_hash": sha("Fixture task"),
            },
            "generations": [],
            "trace": {"sessions": [], "entries": []},
            "scores": {"accuracy": 1},
        }
        if label == "baseline":
            provider = {
                "content": json.dumps(self.answers),
                "response_id": "fixture-response",
                "usage": {
                    "prompt_tokens": inputs,
                    "completion_tokens": outputs,
                    "total_tokens": inputs + outputs,
                },
            }
            save(episode / "crusoe.json", provider)
            save(
                episode / "usage.json",
                {**provider["usage"], "api_calls": calls, "elapsed_seconds": elapsed},
            )
            payload["generations"] = [
                {
                    "prompt": [{"role": "user", "content": "Fixture prompt"}],
                    "completion": provider["content"],
                    **provider,
                }
            ]
        else:
            session = {
                "id": "fixture-native-session",
                "api_call_count": calls,
                "input_tokens": inputs,
                "output_tokens": outputs,
            }
            payload["trace"]["sessions"] = [session]
            usage = {
                "api_calls": calls,
                "input_tokens": inputs,
                "output_tokens": outputs,
            }
            save(episode / f"{label}-audit.json", {**usage, "sessions": [session]})
            save(episode / "usage.json", {**usage, "elapsed_seconds": elapsed})
        canonical = self.state / "telemetry" / episode.name
        save(canonical / "trajectory.json", payload)
        self.publish(label)

    def publish(self, label: str) -> None:
        name = f"{self.run.name}-{label}"
        canonical = self.state / "telemetry" / name
        payload = selection.read(canonical / "trajectory.json")
        revision = telemetry.payload_hash(payload)
        receipt = {
            "trace_id": telemetry.identity(name, "trace"),
            "status": "verified",
            "trajectory_revision": revision,
            "trace_url": "http://localhost/fixture",
        }
        save(canonical / "receipt.json", receipt)
        save(self.run / name / "telemetry.json", receipt)
        observations = []
        for event in telemetry.make_events(name, payload):
            body = event["body"]
            if event["type"] in {"trace-create", "score-create"}:
                continue
            row = {
                **body,
                "type": "GENERATION"
                if event["type"] == "generation-create"
                else "SPAN",
            }
            if "usage" in body:
                row["usageDetails"] = {"total": body["usage"]["totalTokens"]}
            if "output" in row:
                row["output"] = selection.json_value(row["output"])
            observations.append(row)
        self.api[receipt["trace_id"]] = {
            "id": receipt["trace_id"],
            "input": payload["input"],
            "output": payload["output"],
            "metadata": {
                **payload["metadata"],
                "trajectory_revision": revision,
                "run_id": name,
            },
            "observations": observations,
        }

    def load(self, label: str = "baseline") -> dict[str, Any]:
        return selection.candidate(
            self.run, label, self.api.__getitem__, state_root=self.state
        )

    def test_tied_quality_prefers_measured_cost_and_preserves_provenance(self) -> None:
        result = selection.select(
            [self.run], state_root=self.state, fetch=self.api.__getitem__
        )
        self.assertEqual(result["selected_counts"], {self.run.name + "-baseline": 12})
        self.assertTrue(
            all(not c["mass_winning_teacher_eligible"] for c in result["candidates"])
        )
        exported = selection.read(Path(result["export_path"]))["rows"]
        self.assertEqual(len(exported), 12)
        self.assertTrue(
            all(r["provenance"]["source"] == "Langfuse API readback" for r in exported)
        )
        public_report = selection.read(self.state / "trajectory-selection/report.json")
        self.assertEqual(public_report["status"], "ready")
        self.assertNotIn("exports", public_report)
        self.assertNotIn("input", public_report["candidates"][0])
        self.assertEqual(result["heldout_rows"], 0)
        self.assertEqual(result["assignments"], {"training": 10, "validation": 2})
        verified = selection.load_verified_export(
            Path(result["manifest_path"]),
            state_root=self.state,
            fetch=self.api.__getitem__,
        )
        self.assertEqual(len(verified["rows"]), 12)

    def test_quality_precedes_cost_and_partial_answers_never_export(self) -> None:
        baseline, native = self.load(), self.load("v0")
        baseline["by_question"][0]["passed"] = 2
        result = selection.rank([baseline, native])
        chosen = next(r for r in result["tasks"] if r["question_id"] == "dev-top")
        self.assertEqual(chosen["selected_run_id"], native["run_id"])
        native["by_question"][0]["passed"] = 1
        result = selection.rank([baseline, native])
        self.assertFalse(any(r["question_id"] == "dev-top" for r in result["exports"]))

    def test_different_evaluation_bindings_do_not_compete(self) -> None:
        baseline, native = self.load(), self.load("v0")
        native["group_id"] = "another-dataset"
        result = selection.rank([baseline, native])
        self.assertEqual(len(result["exports"]), 24)

    def test_frozen_workflow_or_dataset_change_fails(self) -> None:
        (self.run / "initial-workflow.txt").write_text("Changed workflow")
        with self.assertRaisesRegex(ValueError, "workflow binding"):
            self.load("v0")
        save(self.run / "dataset.json", {"tampered": True})
        with self.assertRaisesRegex(ValueError, "Frozen"):
            self.load()

    def test_changed_independent_report_cannot_reuse_evaluation_snapshot(self) -> None:
        path = self.run / f"{self.run.name}-baseline" / "results.json"
        report = selection.read(path)
        report["by_question"][0]["passed"] = 2
        report["passed"] = 35
        report["task_passed"] = 11
        save(path, report)
        with self.assertRaisesRegex(ValueError, "frozen evaluation snapshot"):
            self.load()

    def test_judge_retention_alone_cannot_make_a_winning_teacher(self) -> None:
        save(
            self.run / "rhi-compare-v1.json",
            {"retained": {"version": 0, "beats_reference": True}},
        )
        result = selection.select(
            [self.run], state_root=self.state, fetch=self.api.__getitem__
        )
        native = next(c for c in result["candidates"] if c["episode"] == "v0")
        self.assertTrue(native["retained_by_mass"])
        self.assertFalse(native["mass_winning_teacher_eligible"])

    def test_heldout_or_failed_never_reaches_api(self) -> None:
        episode = self.run / f"{self.run.name}-baseline"
        for status in (
            {"status": "completed", "split": "heldout"},
            {"status": "failed", "split": "development"},
        ):
            save(episode / "run_status.json", status)
            with self.assertRaisesRegex(ValueError, "excluded"):
                selection.candidate(
                    self.run,
                    "baseline",
                    lambda _: self.fail("API called"),
                    state_root=self.state,
                )

    def test_private_and_reconstructed_records_are_rejected_before_api(self) -> None:
        path = (
            self.state / "telemetry" / f"{self.run.name}-baseline" / "trajectory.json"
        )
        original = selection.read(path)
        for bad in (
            {"input_kind": "reconstructed_from_spec"},
            {"private_reasoning": "private"},
        ):
            payload = copy.deepcopy(original)
            payload["generations"][0].update(bad)
            save(path, payload)
            with self.assertRaisesRegex(ValueError, "[Rr]econstructed|Private"):
                self.load()

    def test_current_receipt_cannot_hide_live_revision_or_answer_change(self) -> None:
        trace_id = telemetry.identity(self.run.name + "-baseline", "trace")
        original = copy.deepcopy(self.api[trace_id])
        self.api[trace_id]["metadata"]["trajectory_revision"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Live Langfuse"):
            self.load()
        self.api[trace_id] = original
        self.api[trace_id]["output"] = {"changed": True}
        with self.assertRaisesRegex(ValueError, "Live Langfuse"):
            self.load()

    def test_claimed_usage_and_missing_observations_fail(self) -> None:
        path = self.run / f"{self.run.name}-v0" / "usage.json"
        original = selection.read(path)
        save(path, {**original, "api_calls": 1})
        with self.assertRaisesRegex(ValueError, "Native usage"):
            self.load("v0")
        trace_id = telemetry.identity(self.run.name + "-baseline", "trace")
        self.api[trace_id]["observations"] = []
        with self.assertRaisesRegex(ValueError, "observations are incomplete"):
            self.load()

    def test_invalid_score_totals_and_boolean_counts_fail(self) -> None:
        report = copy.deepcopy(self.report)
        report["by_question"][0]["passed"] = True
        with self.assertRaises(ValueError):
            selection.validate_report(report, self.public)
        report = copy.deepcopy(self.report)
        report["passed"] = 35
        with self.assertRaisesRegex(ValueError, "totals"):
            selection.validate_report(report, self.public)

    def test_export_digest_and_live_source_are_checked_again(self) -> None:
        result = selection.select(
            [self.run], state_root=self.state, fetch=self.api.__getitem__
        )
        path = Path(result["export_path"])
        original = selection.read(path)
        changed = copy.deepcopy(original)
        changed["rows"][0]["answer"] = {"sql": "SELECT 99"}
        save(path, changed)
        with self.assertRaisesRegex(ValueError, "digest"):
            selection.load_verified_export(
                Path(result["manifest_path"]),
                state_root=self.state,
                fetch=self.api.__getitem__,
            )
        save(path, original)
        trace_id = telemetry.identity(self.run.name + "-baseline", "trace")
        self.api[trace_id]["metadata"]["eligible_for_training"] = False
        with self.assertRaisesRegex(ValueError, "Live Langfuse"):
            selection.load_verified_export(
                Path(result["manifest_path"]),
                state_root=self.state,
                fetch=self.api.__getitem__,
            )

    def test_public_profile_requires_frozen_validation_and_per_database_schema(
        self,
    ) -> None:
        from aya_factory import public_sql_benchmark as benchmark

        public = {
            "benchmark": "public-sql",
            "split": "development",
            "databases": {
                "cars": {"schema": "CREATE TABLE cars(id INTEGER)"},
                "poker": {"schema": "CREATE TABLE poker(id INTEGER)"},
            },
            "questions": [
                {"id": "spider-dev-1", "db_id": "cars", "question": "Car count"},
                {"id": "spider-dev-2", "db_id": "poker", "question": "Poker count"},
            ],
        }
        catalog = {
            "ready": True,
            "dataset_source_sha256": "source",
            "case_manifest_sha256": "cases",
            "executor_sha256": "executor",
            "evaluator_sha256": "evaluator",
        }
        report = {
            "benchmark": "public-sql",
            "split": "development",
            "dataset_sha256": "source",
            "dataset_source_sha256": "source",
            "case_sha256": "cases",
            "case_manifest_sha256": "cases",
            "executor_source_sha256": "executor",
            "evaluator_sha256": "evaluator",
            "passed": 2,
            "total": 2,
            "task_passed": 2,
            "task_total": 2,
            "protocol_valid": True,
            "by_question": [
                {"id": q["id"], "passed": 1, "total": 1} for q in public["questions"]
            ],
        }
        specification = {
            "validation_ids": ["spider-dev-2"],
            "training_ids": ["spider-dev-1"],
            "splits": {"development": public["questions"]},
        }
        path = self.state / "public-manifest.json"
        save(path, specification)
        with (
            patch.object(benchmark, "MANIFEST_PATH", path),
            patch.object(benchmark, "catalog", return_value=catalog),
            patch.object(benchmark, "public_tasks", return_value=public),
        ):
            context = selection.benchmark_context(report, public)
            self.assertEqual(
                context["schemas"]["spider-dev-2"], "CREATE TABLE poker(id INTEGER)"
            )
            selection.validate_report(report, public)
            save(path, {**specification, "validation_ids": ["spider-heldout-3"]})
            with self.assertRaisesRegex(ValueError, "validation IDs"):
                selection.benchmark_context(report, public)
            save(path, specification)
            with self.assertRaisesRegex(ValueError, "pinned source"):
                selection.benchmark_context(
                    {**report, "evaluator_sha256": "changed"}, public
                )


if __name__ == "__main__":
    unittest.main()
