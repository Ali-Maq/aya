"""Integration checks use real GitHub, jq, and isolated Python containers."""

import unittest

from aya_factory.evaluate import isolated, reference, validate_source
from aya_factory.intake import requests, snapshot


class Boundaries(unittest.TestCase):
    def test_live_github_contract_has_identity(self):
        queue = requests()
        self.assertEqual(queue["source"], "GitHub REST API")
        self.assertTrue(any(row["number"] == 1 for row in queue["requests"]))
        frozen = snapshot(1)
        self.assertEqual(len(frozen["target_base"]), 40)
        self.assertEqual(len(frozen["contract_sha256"]), 64)

    def test_reference_distinguishes_false_and_zero(self):
        result = reference(
            [
                {
                    "records": [{"v": False}, {"v": 0}],
                    "columns": [{"label": "v", "path": ["v"], "fallback": "N"}],
                }
            ]
        )[0]
        self.assertEqual(result["rows"], [["N"], [0]])

    def test_shell_import_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_source("import subprocess\ndef export_recipe(p): return {}")

    def test_candidate_cannot_hang_evaluator(self):
        with self.assertRaises(TimeoutError):
            isolated("def export_recipe(p):\n while True: pass\n", [{}], timeout=2)


if __name__ == "__main__":
    unittest.main()
