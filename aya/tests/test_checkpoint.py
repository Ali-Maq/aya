"""Deployment recipes must bind cost, checkpoint identity, and cleanup ownership."""

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aya_factory import checkpoint
from aya_factory.core import save

FLAVOR: dict[str, Any] = {
    "id": checkpoint.FLAVOR,
    "model_name": "Qwen/Qwen3.5-9B",
    "gpu_type": "h100",
    "gpus_per_instance": 1,
    "quantization": "bf16",
    "fused_lora_supported": True,
    "lora_suitable": True,
    "price_per_hour": "5.5",
}
JOB: dict[str, Any] = {
    "id": "ftjob-test",
    "status": "succeeded",
    "fine_tuned_model": "ftmodel-test",
    "model": "base-model",
}


class CheckpointBoundaries(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "0123456789abcdef"
        self.destination = self.directory / "training/deployment"
        self.destination.mkdir(parents=True)
        self.plan = checkpoint.recipe(self.directory, JOB, [FLAVOR], 3600)
        save(self.destination / "recipe.json", self.plan)

    def test_concrete_recipe_uses_schema_field_and_one_gpu_budget(self) -> None:
        self.assertEqual(self.plan["request"]["replicas"], 1)
        self.assertEqual(
            self.plan["request"]["fine_tuned_model"], JOB["fine_tuned_model"]
        )
        self.assertNotIn("fine_tuned_model_id", self.plan["request"])
        self.assertEqual(self.plan["estimated_lifetime_cost_usd"], "5.50")
        shorter = checkpoint.recipe(self.directory, JOB, [FLAVOR], 2700)
        self.assertEqual(shorter["estimated_lifetime_cost_usd"], "4.13")

    def test_budgets_and_incompatible_flavors_are_rejected(self) -> None:
        for seconds in (True, 0, 119, 3601, 3600.0):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                checkpoint.validate_budget(seconds)
        for field, value in (
            ("gpu_type", "h200"),
            ("gpus_per_instance", 2),
            ("fused_lora_supported", False),
            ("model_name", "other"),
        ):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                checkpoint.selected_flavor([{**FLAVOR, field: value}])

    def test_pending_checkpoint_cannot_execute(self) -> None:
        plan = checkpoint.recipe(
            self.directory,
            {**JOB, "status": "running", "fine_tuned_model": None},
            [FLAVOR],
            3600,
        )
        save(self.destination / "recipe.json", plan)
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            checkpoint.execute(self.directory, 3600, plan["recipe_sha256"])

    def test_modified_recipe_or_budget_cannot_execute(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved recipe"):
            checkpoint.execute(self.directory, 2700, self.plan["recipe_sha256"])
        self.plan["request"]["replicas"] = 2
        save(self.destination / "recipe.json", self.plan)
        with self.assertRaisesRegex(ValueError, "approved recipe"):
            checkpoint.execute(self.directory, 3600, self.plan["recipe_sha256"])

    def test_owned_resource_requires_matching_checkpoint_alias_and_replica(
        self,
    ) -> None:
        owned = {
            "id": "resource-one",
            "deployment_name": self.plan["request"]["deployment_name"],
            "fine_tuned_model": JOB["fine_tuned_model"],
            "target_replicas": 1,
        }
        checkpoint.verify_owned(owned, self.plan, "resource-one")
        for field, value in (
            ("id", "other-resource"),
            ("deployment_name", "someone-else"),
            ("fine_tuned_model", "other-model"),
            ("target_replicas", 2),
        ):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                checkpoint.verify_owned(
                    {**owned, field: value}, self.plan, "resource-one"
                )

    def test_cleanup_never_deletes_a_mismatched_resource(self) -> None:
        save(
            self.destination / "creation-started.json",
            {"recipe_sha256": self.plan["recipe_sha256"]},
        )
        save(self.destination / "created.json", {"id": "resource-one"})
        with patch.object(checkpoint, "Client") as factory:
            api = factory.return_value
            api.request.return_value = {
                "id": "resource-one",
                "deployment_name": "another-user",
                "fine_tuned_model": "different",
                "target_replicas": 1,
            }
            receipt = checkpoint.cleanup(self.directory)
            self.assertEqual(receipt["status"], "cleanup_required")
            self.assertIn("identity", receipt["error"])
            self.assertEqual(
                [call.args[0] for call in api.request.call_args_list], ["GET"]
            )

    def test_documented_statuses_do_not_guess_readiness(self) -> None:
        self.assertEqual(checkpoint.deployment_state({"status": "Ready"}), "ready")
        self.assertEqual(
            checkpoint.deployment_state({"status": "Scaling up"}), "scaling up"
        )
        for status in ("running", "healthy", "", None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                checkpoint.deployment_state({"status": status})


if __name__ == "__main__":
    unittest.main()
