"""The SQL executor must contain a candidate even before it earns acceptance."""

import unittest

from aya_factory.intake import snapshot
from aya_factory.profiles import SQL_REPOSITORY
from aya_factory.sql_eval import isolated, validate


class SqlBoundaries(unittest.TestCase):
    def test_live_sql_contract(self):
        frozen = snapshot(1, SQL_REPOSITORY)
        self.assertEqual(frozen["profile"], "crusoe-repository-analyst")
        self.assertEqual(frozen["target_repository"], SQL_REPOSITORY)

    def test_sql_candidate_cannot_hang_controller(self):
        with self.assertRaises(TimeoutError):
            isolated("def execute(payload):\n while True: pass\n", [{}], timeout=2)

    def test_sqlite_cannot_write_container_filesystem(self):
        source = "import sqlite3\ndef execute(payload):\n c=sqlite3.connect('/tmp/aya-test.sqlite')\n c.execute('CREATE TABLE t(x)')\n return {}\n"
        self.assertEqual(isolated(source, [{}]), [{"exception": "OperationalError"}])

    def test_sql_extension_import_rejected(self):
        with self.assertRaises(ValueError):
            validate("import ctypes\ndef execute(payload): return {}")


if __name__ == "__main__":
    unittest.main()
