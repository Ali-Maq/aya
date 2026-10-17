"""Execute SQL against pinned public databases in a restricted container."""

import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .core import run
from .evaluate import PYTHON_IMAGE

RUNNER = r"""
import json, sqlite3, sys, time

FUNCTIONS = set("abs avg char coalesce concat concat_ws count cume_dist date datetime dense_rank first_value floor format group_concat hex ifnull iif instr julianday lag last_value lead length likelihood likely lower ltrim max min mod nth_value ntile nullif percent_rank pow power printf quote rank replace round row_number rtrim sign sqrt strftime substr substring sum time total trim typeof unicode unixepoch unlikely upper".split())
ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}

def execute(item):
    connection = None
    denied = [False]
    try:
        connection = sqlite3.connect("file:/databases/" + item["db_id"] + ".sqlite?mode=ro&immutable=1", uri=True)
        connection.enable_load_extension(False)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1000000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 64)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VDBE_OP, 200000)
        def authorize(action, first, second, database, trigger):
            if action in ALLOWED:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in FUNCTIONS:
                return sqlite3.SQLITE_OK
            denied[0] = True
            return sqlite3.SQLITE_DENY
        connection.set_authorizer(authorize)
        deadline = time.monotonic() + 3
        steps = [0]
        def progress():
            steps[0] += 1000
            return int(steps[0] > 3000000 or time.monotonic() > deadline)
        connection.set_progress_handler(progress, 1000)
        cursor = connection.execute(item["sql"])
        if cursor.description is None:
            return {"error": "read_only"}
        rows = cursor.fetchmany(1001)
        if len(rows) > 1000:
            return {"error": "result_limit"}
        def cell(value):
            return {"blob_hex": value.hex()} if isinstance(value, bytes) else value
        result = {"columns": [col[0] for col in cursor.description], "rows": [[cell(v) for v in row] for row in rows]}
        if len(json.dumps(result).encode()) > 131072:
            return {"error": "result_limit"}
        return result
    except (sqlite3.Error, MemoryError) as error:
        if isinstance(error, sqlite3.OperationalError) and "interrupted" in str(error):
            return {"error": "query_limit"}
        return {"error": "read_only" if denied[0] else "query_error"}
    finally:
        if connection is not None:
            connection.close()

items = json.load(sys.stdin)
print(json.dumps([execute(item) for item in items], allow_nan=False))
"""


def execute_queries(
    database_root: Path, requests: list[dict[str, str]], *, timeout: int = 90
) -> list[dict[str, Any]]:
    """Keep candidate SQL and private oracle SQL outside host execution."""
    root = database_root.resolve(strict=True)
    if not requests or len(requests) > 100:
        raise ValueError("Provide between one and one hundred SQL requests")
    for item in requests:
        if set(item) != {"db_id", "sql"}:
            raise ValueError("SQL requests require db_id and sql")
        if not re.fullmatch(r"[a-zA-Z0-9_]{1,80}", item["db_id"]):
            raise ValueError("Invalid database identity")
        path = root / (item["db_id"] + ".sqlite")
        if path.is_symlink() or not path.is_file():
            raise ValueError("Database file missing or linked")
        if not isinstance(item["sql"], str) or not 0 < len(item["sql"]) <= 20000:
            raise ValueError("SQL text exceeds the request boundary")
    name = "aya-public-sql-" + uuid.uuid4().hex[:12]
    try:
        output = run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--memory",
                "256m",
                "--pids-limit",
                "32",
                "--cpus",
                "1",
                "--user",
                "65534:65534",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",  # noqa: S108 -- Private container tmpfs.
                "--mount",
                f"type=bind,src={root},dst=/databases,readonly",
                "-i",
                PYTHON_IMAGE,
                "python3",
                "-I",
                "-B",
                "-c",
                RUNNER,
            ],
            data=json.dumps(requests),
            timeout=timeout,
        )
        values = json.loads(output)
        if not isinstance(values, list) or len(values) != len(requests):
            raise ValueError("Invalid public SQL result envelope")
        return values
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
