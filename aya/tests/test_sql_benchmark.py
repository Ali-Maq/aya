"""The workflow benchmark must hide oracles and reject literal answers."""

import json
import unittest

from aya_factory import sql_benchmark as benchmark
from aya_factory.sql_eval import FIELDS, SCHEMA, oracle

# This fixture checks benchmark scoring. Runtime evaluation uses the accepted module.
EXECUTOR = f"""import sqlite3
def execute(payload):
    with sqlite3.connect(':memory:') as connection:
        connection.execute({SCHEMA!r})
        connection.executemany('INSERT INTO repositories VALUES(?,?,?,?,?,?,?,?)',
            [tuple(record[key] for key in {FIELDS!r}) for record in payload['records']])
        connection.execute('PRAGMA query_only=ON')
        cursor=connection.execute(payload['sql'])
        return {{'columns':[item[0] for item in cursor.description],
                 'rows':[list(row) for row in cursor.fetchall()]}}
"""


class SqlBenchmark(unittest.TestCase):
    def test_public_tasks_exclude_oracles_and_holdout(self) -> None:
        development = benchmark.public_tasks("development", 42)
        heldout = benchmark.public_tasks("heldout", 43)
        self.assertEqual(len(development["questions"]), 12)
        self.assertEqual(len(heldout["questions"]), 12)
        self.assertFalse(
            {item["id"] for item in development["questions"]}
            & {item["id"] for item in heldout["questions"]}
        )
        for item in development["questions"] + heldout["questions"]:
            self.assertEqual(set(item), {"id", "question"})
        self.assertNotIn("expected_sql", json.dumps(development))
        self.assertNotIn("refuse", json.dumps(development))
        self.assertNotIn("refuse", json.dumps(heldout))

    def test_seed_changes_data_without_changing_contract(self) -> None:
        self.assertEqual(benchmark.dataset(42), benchmark.dataset(42))
        self.assertNotEqual(
            benchmark.dataset(42), benchmark.dataset(42 + benchmark.SEED_OFFSETS[1])
        )
        self.assertNotIn("delta", {row["owner"] for row in benchmark.dataset(42)})
        self.assertIn("delta", {row["owner"] for row in benchmark.dataset(43)})
        for split in benchmark.SPLITS:
            self.assertEqual(
                sum(bool(case.get("refuse")) for case in benchmark.cases(split)), 2
            )
            for case in benchmark.cases(split):
                if not case.get("refuse"):
                    for seed in (42, 104771, 209801):
                        self.assertIsInstance(
                            oracle(benchmark.dataset(seed), case["expected_sql"])[
                                "rows"
                            ],
                            list,
                        )

    def test_isolated_scoring_rejects_snapshot_hardcoding(self) -> None:
        answers = {
            case["id"]: {"refused": True}
            if case.get("refuse")
            else {"sql": case["expected_sql"]}
            for case in benchmark.cases("development")
        }
        first_rows = oracle(benchmark.dataset(42), answers["dev-top"]["sql"])["rows"]
        literal_rows = [
            f"SELECT '{repo.replace(chr(39), chr(39) * 2)}', {stars}"
            for repo, stars in first_rows
        ]
        answers["dev-top"] = {"sql": " UNION ALL ".join(literal_rows)}
        report = benchmark.evaluate(answers, "development", 42, EXECUTOR)
        self.assertEqual(report["total"], 36)
        self.assertEqual(report["task_total"], 12)
        self.assertEqual(report["task_passed"], 11)
        self.assertEqual(report["passed"], 34)
        self.assertEqual({item["id"] for item in report["failures"]}, {"dev-top"})


if __name__ == "__main__":
    unittest.main()
