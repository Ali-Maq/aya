"""Offline checks for workflow retention and trace export boundaries."""

import json
import unittest
from typing import Any

from aya_factory import mass_loop, telemetry


def report(passed: int) -> dict[str, Any]:
    return {
        "split": "development",
        "passed": passed,
        "total": 36,
        "task_passed": passed // 3,
        "task_total": 12,
        "dataset_sha256": "dataset",
        "case_sha256": "cases",
        "executor_source_sha256": "executor",
    }


class MassBoundaries(unittest.TestCase):
    def test_selection_requires_strict_development_improvement(self) -> None:
        self.assertEqual(mass_loop.choose_workflow(report(33), report(36)), "v1")
        self.assertEqual(mass_loop.choose_workflow(report(36), report(36)), "v0")
        self.assertEqual(mass_loop.choose_workflow(report(36), report(33)), "v0")

    def test_selection_rejects_incomparable_or_invalid_reports(self) -> None:
        for key, value in (
            ("split", "heldout"),
            ("dataset_sha256", "other"),
            ("case_sha256", "other"),
            ("executor_source_sha256", "other"),
            ("total", 39),
            ("task_total", 13),
            ("passed", True),
            ("passed", -1),
            ("passed", 37),
            ("task_passed", 13),
            ("total", 0),
        ):
            with self.subTest(key=key, value=value):
                candidate = {**report(36), key: value}
                with self.assertRaises(ValueError):
                    mass_loop.choose_workflow(report(36), candidate)

    def test_parser_requires_an_object_and_run_ids_cannot_escape_state(self) -> None:
        self.assertEqual(
            mass_loop.parse_answers('```json\n{"q":{"refused":true}}\n```'),
            {"q": {"refused": True}},
        )
        for text in ("[]", "null", '"answer"', '{"q":1} trailing'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                mass_loop.parse_answers(text)
        for run_id in ("../private", "a" * 17, "A" * 16):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                mass_loop.directory_for(run_id)

    def test_public_scores_must_share_the_frozen_evaluator(self) -> None:
        first = {**report(33), "evaluator_sha256": "original"}
        second = {**report(36), "evaluator_sha256": "changed"}
        with self.assertRaisesRegex(ValueError, "different evaluators"):
            mass_loop.choose_workflow(first, second)

    def test_export_requires_provenance_and_removes_private_fields(self) -> None:
        payload = {
            "metadata": {
                "split": "development",
                "eligible_for_training": True,
                "version_hash": "v",
                "dataset_hash": "d",
                "contract_hash": "c",
            },
            "output": {
                "ok": True,
                "reasoning_content": "private-thought",
                "heldout_answers": "private-answer",
            },
            "trace": {
                "entries": [
                    {"split": "heldout", "content": "private-test"},
                    {"content": "Bearer private-token <think>hidden</think> visible"},
                ]
            },
        }
        exported = telemetry.training_record("test", payload)
        self.assertIsNotNone(exported)
        serialized = json.dumps(exported)
        for private in (
            "private-thought",
            "private-answer",
            "private-test",
            "private-token",
            "hidden",
        ):
            self.assertNotIn(private, serialized)
        self.assertIn("visible", serialized)
        for split in ("heldout", "test", "validation", "unspecified"):
            with self.subTest(split=split):
                payload["metadata"]["split"] = split
                self.assertIsNone(telemetry.training_record("test", payload))
        payload["metadata"]["split"] = "dev"
        del payload["metadata"]["dataset_hash"]
        self.assertIsNone(telemetry.training_record("test", payload))

    def test_trace_capture_is_bounded_and_ids_are_stable(self) -> None:
        payload = {
            "trace": {
                "entries": [
                    {"id": str(i), "session": "s", "kind": "message", "content": "ok"}
                    for i in range(telemetry.MAX_ENTRIES + 7)
                ]
            }
        }
        first = telemetry.make_events("test", payload)
        second = telemetry.make_events("test", payload)
        self.assertEqual(len(first), telemetry.MAX_ENTRIES + 1)
        self.assertEqual(
            [row["body"]["id"] for row in first], [row["body"]["id"] for row in second]
        )
        self.assertLessEqual(len(telemetry.clean("x" * 30000)), telemetry.MAX_TEXT + 20)

    def test_heldout_telemetry_contains_metrics_only(self) -> None:
        payload = {
            "name": "Held-out evaluation",
            "metadata": {
                "split": "heldout",
                "eligible_for_training": True,
                "version_hash": "v",
            },
            "input": {"question": "PRIVATE_QUESTION"},
            "output": {"answer": "PRIVATE_ANSWER"},
            "workflow": "PRIVATE_WORKFLOW",
            "generations": [
                {"prompt": "PRIVATE_PROMPT", "completion": "PRIVATE_COMPLETION"}
            ],
            "trace": {
                "sessions": [{"id": "private-session"}],
                "entries": [{"content": "PRIVATE_TOOL"}],
            },
            "scores": {"heldout_accuracy": 0.75, "private-case-name": 1.0},
        }
        projected = telemetry.project(payload)
        self.assertEqual(projected["metadata"]["split"], "heldout")
        self.assertIs(projected["metadata"]["eligible_for_training"], False)
        self.assertEqual(projected["scores"], {"heldout_accuracy": 0.75})
        self.assertNotIn("PRIVATE", json.dumps(projected))
        self.assertNotIn("private-", json.dumps(projected))
        events = telemetry.make_events("heldout-test", payload)
        self.assertEqual(
            [row["type"] for row in events], ["trace-create", "score-create"]
        )
        self.assertNotIn("PRIVATE", json.dumps(events))
        self.assertIsNone(telemetry.training_record("heldout-test", payload))


if __name__ == "__main__":
    unittest.main()
