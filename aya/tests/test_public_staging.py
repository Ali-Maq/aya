"""Exercise the native staging script locally, without a worker or model call."""

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from aya_factory import agents, mass_loop
from aya_factory.core import sha


class PublicStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "episode"
        public = mass_loop.public_input("repository-fixture", "development")
        self.files = mass_loop.episode_files(
            "repository-fixture", "development", public, "Fixture task"
        )

    def stage(
        self, files: dict[str, Any] | None = None, workspace: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        encoded = base64.b64encode(
            json.dumps(files if files is not None else self.files).encode()
        ).decode()
        return subprocess.run(
            [
                sys.executable,
                "-c",
                agents.STAGE_PUBLIC_INPUTS,
                str(workspace or self.workspace),
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_exact_public_files_have_verified_native_digests(self) -> None:
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(
            set(receipt["files"]),
            {"public-tasks.json", "dataset.json", "contract.json"},
        )
        for name, value in self.files.items():
            self.assertEqual(json.loads((self.workspace / name).read_text()), value)
            self.assertEqual(
                receipt["files"][name], sha((self.workspace / name).read_bytes())
            )
        self.assertTrue(receipt["verified"])

    def test_existing_file_is_not_replaced_and_other_files_are_not_written(
        self,
    ) -> None:
        self.workspace.mkdir()
        original = self.workspace / "dataset.json"
        original.write_text("existing input")
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertEqual(original.read_text(), "existing input")
        self.assertEqual({p.name for p in self.workspace.iterdir()}, {"dataset.json"})

    def test_symlink_files_and_directories_are_rejected(self) -> None:
        target = self.root / "private.json"
        target.write_text("private content")
        self.workspace.mkdir()
        (self.workspace / "contract.json").symlink_to(target)
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertEqual(target.read_text(), "private content")
        alias = self.root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        self.assertNotEqual(self.stage(workspace=alias).returncode, 0)

    def test_unknown_names_path_traversal_and_non_object_json_are_rejected(
        self,
    ) -> None:
        for name, value in (
            ("../escape.json", {}),
            ("results.json", {}),
            ("contract.json", []),
        ):
            files = {**self.files, name: value}
            self.assertNotEqual(self.stage(files).returncode, 0)
        self.assertFalse(self.workspace.exists())
        self.assertFalse((self.root / "escape.json").exists())

    def test_current_split_is_required_and_contract_has_no_evaluation_files(
        self,
    ) -> None:
        development = mass_loop.public_input("repository-fixture", "development")
        heldout = mass_loop.public_input("repository-fixture", "heldout")
        with self.assertRaisesRegex(ValueError, "current episode split"):
            mass_loop.episode_files(
                "repository-fixture", "heldout", development, "Task"
            )
        with self.assertRaisesRegex(ValueError, "current episode split"):
            mass_loop.episode_files(
                "repository-fixture", "development", heldout, "Task"
            )
        files = mass_loop.episode_files(
            "repository-fixture", "heldout", heldout, "Task"
        )
        self.assertEqual(files["public-tasks.json"], heldout)
        self.assertEqual(
            set(files["contract.json"]), {"task", "split", "output", "budgets"}
        )
        self.assertNotIn("expected_sql", json.dumps(files))
        self.assertNotIn("source_url", json.dumps(files))

    def test_bundle_limit_precedes_native_launch_and_native_file_writes(self) -> None:
        files = {**self.files, "contract.json": {"padding": "x" * 70_000}}
        with patch.object(agents, "run") as command:
            with self.assertRaisesRegex(ValueError, "size limit"):
                agents.stage_public_inputs(
                    str(self.workspace), files, self.root, Mock(), "test"
                )
            command.assert_not_called()
        self.assertNotEqual(self.stage(files).returncode, 0)
        self.assertFalse(self.workspace.exists())


if __name__ == "__main__":
    unittest.main()
