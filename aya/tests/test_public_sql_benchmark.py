"""Check public-data isolation and real read-only SQLite execution."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aya_factory import public_sql_benchmark as benchmark
from aya_factory.public_db_executor import execute_queries


class PublicSqlBenchmark(unittest.TestCase):
    def test_frozen_public_input_has_no_oracles_and_disjoint_databases(self) -> None:
        development = benchmark.public_tasks("development")
        heldout = benchmark.public_tasks("heldout")
        self.assertEqual(len(development["questions"]), 12)
        self.assertEqual(len(heldout["questions"]), 6)
        self.assertFalse(set(development["databases"]) & set(heldout["databases"]))
        for public in [development, heldout]:
            for question in public["questions"]:
                self.assertEqual(set(question), {"id", "db_id", "question"})
            for database in public["databases"].values():
                self.assertIn("CREATE TABLE", database["schema"].upper())
                for sample in database["sample_rows"].values():
                    self.assertLessEqual(len(sample["rows"]), 2)
        serialized = json.dumps(development)
        self.assertNotIn("https://", json.dumps(development["provenance"]))
        for private_key in ['"query"', '"SQL"', '"expected_sql"', '"expected_rows"']:
            self.assertNotIn(private_key, serialized)

    def test_real_gold_queries_pass_and_incorrect_column_count_fails(self) -> None:
        root, manifest = benchmark._verify()
        for split in ("development", "heldout"):
            cases = benchmark._cases(split, root, manifest)
            answers = {task["id"]: {"sql": task["query"]} for task in cases}
            result = benchmark.evaluate(answers, split)
            self.assertEqual(result["passed"], len(cases))
            self.assertTrue(result["protocol_valid"])
            if split == "development":
                answers[cases[0]["id"]] = {"sql": "SELECT 1, 2, 3, 4"}
                result = benchmark.evaluate(answers, split)
                self.assertEqual(result["passed"], len(cases) - 1)
                self.assertEqual(
                    result["failures"],
                    [{"id": cases[0]["id"], "reason": "result_mismatch"}],
                )
                answers["extra-question"] = {"sql": "SELECT 1"}
                invalid = benchmark.evaluate(answers, split)
                self.assertFalse(invalid["protocol_valid"])
                self.assertEqual(invalid["passed"], 0)

    def test_sql_cannot_write_attach_load_extensions_or_run_forever(self) -> None:
        root, manifest = benchmark._verify()
        database = manifest["splits"]["development"][0]["db_id"]
        path = root / "databases" / f"{database}.sqlite"
        before = benchmark._digest(path)
        sql = [
            "CREATE TABLE intrusion(x)",
            "ATTACH DATABASE '/tmp/other.sqlite' AS external",
            "PRAGMA user_version=9",
            "SELECT load_extension('/tmp/extension')",
            "SELECT readfile('/etc/passwd')",
            "SELECT 1; SELECT 2",
            "WITH RECURSIVE t(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM t) SELECT SUM(x) FROM t",
        ]
        results = execute_queries(
            root / "databases", [{"db_id": database, "sql": value} for value in sql]
        )
        self.assertTrue(all("error" in result for result in results))
        self.assertEqual(results[-1], {"error": "query_limit"})
        self.assertEqual(benchmark._digest(path), before)
        self.assertFalse((root / "databases" / "other.sqlite").exists())

    def test_row_comparison_preserves_duplicates_order_and_null(self) -> None:
        a = {"columns": ["a"], "rows": [[None], [1], [1]]}
        b = {"columns": ["alias"], "rows": [[1], [None], [1]]}
        self.assertTrue(benchmark._same_rows(a, b, False))
        self.assertFalse(benchmark._same_rows(a, b, True))
        self.assertFalse(
            benchmark._same_rows(a, {"columns": ["a"], "rows": [[None], [1]]}, False)
        )

    def test_dataset_tampering_is_rejected_before_execution(self) -> None:
        root, manifest = benchmark._verify()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            for relative in manifest["files"]:
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / relative, target)
            database = next(
                name for name in manifest["files"] if name.endswith(".sqlite")
            )
            with (temporary / database).open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                benchmark.public_tasks("development", temporary)


if __name__ == "__main__":
    unittest.main()
