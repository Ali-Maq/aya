"""Offline tests for training provenance, split leakage, and submission bounds."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aya_factory import sql_benchmark, training
from aya_factory.core import save, sha


class TrainingBoundaries(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.selected = self.directory / "selected"
        self.selected.mkdir()
        (self.directory / "selected-workflow.txt").write_text("test workflow")
        (self.directory / "task.txt").write_text("test task contract")
        public = sql_benchmark.public_tasks("development", 42)
        answers = {task["id"]: {"sql": "SELECT 1"} for task in public["questions"]}
        # Fixture scores test export gates. They are not a benchmark result.
        report = {
            "split": "development",
            "dataset_sha256": "fixture-dataset",
            "dataset_seeds": [42, 43, 44],
            "protocol_valid": True,
            "by_question": [{"id": key, "passed": 3, "total": 3} for key in answers],
        }
        trajectory = {
            "input": public,
            "output": answers,
            "metadata": {
                "split": "development",
                "eligible_for_training": True,
                "version_hash": sha("test workflow"),
                "contract_hash": sha("test task contract"),
                "dataset_hash": report["dataset_sha256"],
                "trajectory_revision": "fixture-revision",
            },
            "provenance": {
                "source": "Langfuse API readback",
                "trace_id": "fixture-trace",
                "trajectory_revision": "fixture-revision",
            },
        }
        save(self.directory / "dataset.json", public)
        save(self.selected / "public-tasks.json", public)
        save(self.selected / "queries.json", answers)
        save(self.selected / "results.json", report)
        save(self.selected / "training-export.json", trajectory)
        save(
            self.selected / "telemetry.json",
            {
                "status": "verified",
                "trace_id": "fixture-trace",
                "trajectory_revision": "fixture-revision",
                "trace_url": "http://localhost:3001/fixture-only",
                "training_export": str(self.selected / "training-export.json"),
            },
        )

    def change(self, filename: str, key: str, value: Any) -> None:
        path = self.selected / filename
        data = json.loads(path.read_text())
        data[key] = value
        save(path, data)

    def test_export_splits_questions_and_contains_only_final_answers(self) -> None:
        manifest = training.prepare(self.directory, self.selected)
        self.assertEqual(manifest["training_rows"], 10)
        self.assertEqual(manifest["validation_rows"], 2)
        ids = manifest["question_ids"]
        self.assertFalse(set(ids["training"]) & set(ids["validation"]))
        self.assertEqual(set(ids["validation"]), training.VALIDATION_IDS)
        self.assertEqual(manifest["heldout_rows"], 0)
        rows = [
            json.loads(line)
            for line in (self.directory / "training/training.jsonl")
            .read_text()
            .splitlines()
        ]
        for row in rows:
            self.assertEqual(
                [message["role"] for message in row["messages"]],
                ["system", "user", "assistant"],
            )
            self.assertEqual(
                set(json.loads(row["messages"][1]["content"])), {"schema", "question"}
            )
            self.assertNotIn("reasoning", row["messages"][2]["content"])

    def test_pending_readback_cannot_release_training_data(self) -> None:
        self.change("telemetry.json", "status", "accepted_pending")
        with self.assertRaisesRegex(RuntimeError, "verified Langfuse"):
            training.prepare(self.directory, self.selected)
        self.assertFalse((self.directory / "training").exists())

    def test_output_tampering_is_rejected(self) -> None:
        self.change("queries.json", "dev-top", {"sql": "SELECT 2"})
        with self.assertRaisesRegex(RuntimeError, "outputs differ"):
            training.prepare(self.directory, self.selected)

    def test_evaluation_split_cannot_be_used_for_training(self) -> None:
        self.change("results.json", "split", "heldout")
        with self.assertRaisesRegex(RuntimeError, "development record"):
            training.prepare(self.directory, self.selected)

    def test_export_requires_explicit_eligibility_and_matching_hashes(self) -> None:
        path = self.selected / "training-export.json"
        original = json.loads(path.read_text())
        for key, value in (
            ("eligible_for_training", False),
            ("split", "heldout"),
            ("dataset_hash", "changed"),
            ("version_hash", "changed"),
            ("contract_hash", "changed"),
            ("trajectory_revision", "changed"),
        ):
            with self.subTest(key=key):
                data = json.loads(json.dumps(original))
                data["metadata"][key] = value
                save(path, data)
                with self.assertRaises(RuntimeError):
                    training.prepare(self.directory, self.selected)

    def test_heldout_ids_cannot_hide_inside_development_metadata(self) -> None:
        public_path = self.selected / "public-tasks.json"
        public = json.loads(public_path.read_text())
        old = public["questions"][0]["id"]
        public["questions"][0]["id"] = "heldout-private"
        save(public_path, public)
        save(self.directory / "dataset.json", public)
        export_path = self.selected / "training-export.json"
        trajectory = json.loads(export_path.read_text())
        trajectory["input"] = public
        trajectory["output"]["heldout-private"] = trajectory["output"].pop(old)
        save(export_path, trajectory)
        save(self.selected / "queries.json", trajectory["output"])
        report = json.loads((self.selected / "results.json").read_text())
        report["by_question"][0]["id"] = "heldout-private"
        save(self.selected / "results.json", report)
        with self.assertRaisesRegex(RuntimeError, "question identities"):
            training.prepare(self.directory, self.selected)

    def test_a_question_must_pass_every_dataset_variant(self) -> None:
        report = json.loads((self.selected / "results.json").read_text())
        report["by_question"][0]["passed"] = 2
        save(self.selected / "results.json", report)
        with self.assertRaisesRegex(RuntimeError, "ten passing"):
            training.prepare(self.directory, self.selected)

    def test_zero_or_boolean_score_counts_are_invalid(self) -> None:
        path = self.selected / "results.json"
        original = json.loads(path.read_text())
        for passed, total in ((0, 0), (True, 3), (4, 3)):
            with self.subTest(passed=passed, total=total):
                report = json.loads(json.dumps(original))
                report["by_question"][0].update(passed=passed, total=total)
                save(path, report)
                with self.assertRaisesRegex(RuntimeError, "score counts"):
                    training.prepare(self.directory, self.selected)

    def test_unknown_submission_outcome_never_retries_provider_call(self) -> None:
        training.prepare(self.directory, self.selected)
        save(self.directory / "training/submission-started.json", {"fixture": True})
        with self.assertRaisesRegex(RuntimeError, "unknown outcome"):
            training.prepare_and_submit(self.directory, self.selected)

    def test_public_contract_cannot_silently_authorize_training(self) -> None:
        manifest = training.prepare(self.directory, self.selected)
        save(
            self.directory / "github-request.json",
            {
                "contract": {
                    "benchmark": "public-sql",
                    "training_export": {"automatic_training_submission": False},
                }
            },
        )
        with self.assertRaisesRegex(RuntimeError, "does not authorize"):
            training.submit_prepared(self.directory, manifest)
        self.assertFalse((self.directory / "training/submission-started.json").exists())

    def test_changed_training_file_cannot_reach_upload(self) -> None:
        manifest = training.prepare(self.directory, self.selected)
        (self.directory / "training/training.jsonl").write_text("modified")
        with self.assertRaisesRegex(RuntimeError, "corpus changed"):
            training.submit_prepared(self.directory, manifest)


if __name__ == "__main__":
    unittest.main()
