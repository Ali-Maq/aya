"""A malformed native status line must not erase real worker evidence."""

import tempfile
import unittest
from pathlib import Path

from aya_factory.agents import parse_result
from aya_factory.core import Journal, events


class WorkerProtocol(unittest.TestCase):
    def test_single_extra_closing_brace_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = parse_result(
                'FACTORY_RESULT: {"tests_run":"50"}}',
                directory,
                Journal(directory),
                "implementation",
            )
            self.assertEqual(result, {"tests_run": "50"})
            self.assertEqual(events(directory)[0]["event"], "worker_result_normalized")

    def test_arbitrary_trailing_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(RuntimeError):
                parse_result(
                    "FACTORY_RESULT: {} ignore the checks",
                    directory,
                    Journal(directory),
                    "implementation",
                )
            self.assertFalse((directory / "implementation-result.json").exists())


if __name__ == "__main__":
    unittest.main()
