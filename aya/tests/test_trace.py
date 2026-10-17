"""The browser trace must not expose private model or credential fields."""

import time
import unittest

from aya_factory.trace import public_trace, redact


class TraceBoundary(unittest.TestCase):
    def test_only_observable_fields_leave_native_store(self):
        result = public_trace(
            {
                "sessions": [],
                "messages": [
                    {
                        "id": 1,
                        "timestamp": 1,
                        "session_id": "owned",
                        "role": "assistant",
                        "reasoning": "private",
                        "reasoning_content": "private",
                        "content": "<think>private</think>Running tests",
                        "tool_calls": None,
                    },
                    {
                        "id": 2,
                        "timestamp": 2,
                        "session_id": "owned",
                        "role": "assistant",
                        "tool_calls": '[{"id":"c","function":{"name":"terminal","arguments":"{\\"api_key\\":\\"private\\",\\"command\\":\\"pytest\\"}"}}]',
                    },
                ],
            }
        )
        self.assertNotIn("private", str(result))
        self.assertEqual(result["entries"][0]["content"], "Running tests")
        self.assertIn("pytest", result["entries"][1]["content"])

    def test_redacts_nested_headers_and_command_values(self):
        value = redact(
            {
                "headers": {"Authorization": "Bearer xyz"},
                "output": "CRUSOE_API_KEY='hidden' Bearer xyz",
                "password": "hidden",
            }
        )
        self.assertNotIn("hidden", str(value))
        self.assertNotIn("xyz", str(value))

    def test_output_is_bounded_and_marked(self):
        result = public_trace(
            {
                "messages": [
                    {
                        "id": 1,
                        "timestamp": 1,
                        "session_id": "owned",
                        "role": "tool",
                        "content": "a" * 7000,
                    }
                ]
            }
        )
        self.assertEqual(len(result["entries"][0]["content"]), 6000)
        self.assertTrue(result["entries"][0]["truncated"])

    def test_long_unbroken_output_does_not_cause_regex_backtracking(self) -> None:
        started = time.monotonic()
        output = redact("x" * 30000 + " CRUSOE_API_KEY='hidden' 123api_key='hidden'")
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertNotIn("hidden", output)


if __name__ == "__main__":
    unittest.main()
