"""Independent SQLite comparisons and bounded execution for the SQL capability."""

import ast
import json
import random
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .core import run, save, sha
from .evaluate import PYTHON_IMAGE

FIELDS = ["repo", "owner", "stars", "forks", "issues", "license", "description", "url"]
SCHEMA = "CREATE TABLE repositories(repo TEXT, owner TEXT, stars INTEGER, forks INTEGER, issues INTEGER, license TEXT, description TEXT, url TEXT)"
RUNNER = """import json,sys
p=json.load(sys.stdin);n={"__name__":"query"}
exec(compile(p["source"],"query.py","exec"),n)
out=[]
for item in p["requests"]:
 try: out.append(n["execute"](item))
 except Exception as e: out.append({"exception":type(e).__name__})
print(json.dumps(out,allow_nan=False))
"""


def validate(source: str) -> None:
    if len(source.encode()) > 60_000:
        raise ValueError("SQL component exceeds source limit")
    tree = ast.parse(source)
    allowed = {"sqlite3", "json", "re", "typing", "collections", "math"}
    blocked = {
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "getattr",
        "setattr",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
    }
    if not any(
        isinstance(n, ast.FunctionDef) and n.name == "execute" for n in tree.body
    ):
        raise ValueError("Missing execute function")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] not in allowed for a in node.names
        ):
            raise ValueError("SQL component imports an unsupported module")
        if isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or "").split(".")[0] not in allowed
        ):
            raise ValueError("SQL component imports an unsupported module")
        if isinstance(node, ast.Name) and node.id in blocked:
            raise ValueError("SQL component uses a prohibited operation")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__")
            or node.attr in {"enable_load_extension", "load_extension", "backup"}
        ):
            raise ValueError("SQL component accesses prohibited internals")


def isolated(source: str, requests: list[Any], timeout: int = 15) -> list[Any]:
    validate(source)
    name = "aya-sql-" + uuid.uuid4().hex[:12]
    try:
        result = run(
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
                "128m",
                "--pids-limit",
                "32",
                "--cpus",
                "1",
                "--user",
                "65534:65534",
                "-i",
                PYTHON_IMAGE,
                "python3",
                "-I",
                "-B",
                "-c",
                RUNNER,
            ],
            data=json.dumps({"source": source, "requests": requests}),
            timeout=timeout,
        )
        values = json.loads(result)
        if not isinstance(values, list) or len(values) != len(requests):
            raise ValueError("Invalid SQL result envelope")
        return values
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


def oracle(records: list[dict[str, Any]], query: str) -> dict[str, Any]:
    with sqlite3.connect(":memory:") as connection:
        connection.execute(SCHEMA)
        connection.executemany(
            "INSERT INTO repositories VALUES(?,?,?,?,?,?,?,?)",
            [tuple(r[k] for k in FIELDS) for r in records],
        )
        cursor = connection.execute(query)
        return {
            "columns": [x[0] for x in cursor.description],
            "rows": [list(x) for x in cursor.fetchall()],
        }


def cases(seed: int) -> tuple[list[Any], list[Any]]:
    rng = random.Random(seed)
    inputs: list[Any] = []
    expected: list[Any] = []
    queries = [
        "SELECT repo, stars FROM repositories ORDER BY stars DESC, repo LIMIT 3",
        "SELECT owner, SUM(stars) AS total FROM repositories GROUP BY owner ORDER BY owner",
        "SELECT COUNT(*) AS total, MIN(stars) AS smallest, MAX(stars) AS largest FROM repositories",
        "SELECT repo, license FROM repositories WHERE license IS NULL ORDER BY repo",
        "SELECT description FROM repositories WHERE stars=0 ORDER BY repo",
        "WITH x AS (SELECT * FROM repositories WHERE stars >= 5) SELECT repo, forks FROM x ORDER BY repo",
        "SELECT 'DROP TABLE' AS text, 0 AS zero, NULL AS empty",
        "/* read query */ SELECT owner, COUNT(*) AS count FROM repositories GROUP BY owner ORDER BY owner",
    ]
    for index in range(12):
        records = [
            {
                "repo": f"o{j % 3}/r{j}",
                "owner": f"o{j % 3}",
                "stars": rng.choice([0, 5, 11, 42, 999]),
                "forks": rng.randrange(20),
                "issues": rng.randrange(9),
                "license": rng.choice([None, "MIT", "Apache-2.0"]),
                "description": rng.choice([None, "東京", "quote' and DROP TABLE", ""]),
                "url": f"https://github.com/o{j % 3}/r{j}",
            }
            for j in range(index)
        ]
        for query in queries:
            inputs.append({"records": records, "sql": query})
            expected.append(oracle(records, query))
    base = {
        "repo": "a/r",
        "owner": "a",
        "stars": 0,
        "forks": 0,
        "issues": 0,
        "license": None,
        "description": "x",
        "url": "https://github.com/a/r",
    }
    bad: list[tuple[Any, str]] = [
        (None, "invalid_request"),
        ({}, "invalid_request"),
        ({"records": [1], "sql": "SELECT 1"}, "invalid_request"),
        ({"records": [{**base, "stars": True}], "sql": "SELECT 1"}, "invalid_request"),
        ({"records": [{**base, "stars": -1}], "sql": "SELECT 1"}, "invalid_request"),
        ({"records": [{**base, "extra": "x"}], "sql": "SELECT 1"}, "invalid_request"),
        ({"records": [base] * 501, "sql": "SELECT 1"}, "limit_exceeded"),
        ({"records": [base], "sql": " "}, "invalid_request"),
        ({"records": [], "sql": "SELECT missing FROM repositories"}, "query_error"),
        ({"records": [], "sql": "SELECT * FROM absent"}, "query_error"),
        ({"records": [], "sql": "SELECT 1; SELECT 2"}, "query_error"),
        (
            {"records": [base] * 101, "sql": "SELECT * FROM repositories"},
            "limit_exceeded",
        ),
        (
            {
                "records": [],
                "sql": "SELECT " + ",".join(f"1 AS c{i}" for i in range(21)),
            },
            "limit_exceeded",
        ),
        (
            {
                "records": [],
                "sql": "WITH RECURSIVE t(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM t) SELECT SUM(x) FROM t",
            },
            "limit_exceeded",
        ),
    ]
    for query in [
        "DELETE FROM repositories",
        "DROP TABLE repositories",
        "UPDATE repositories SET stars=9",
        "CREATE TABLE extra(x)",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA user_version",
        "BEGIN",
        "SELECT load_extension('/tmp/anything')",
    ]:
        bad.append(({"records": [base], "sql": query}, "read_only"))  # noqa: PERF401
    for payload, code in bad:
        inputs.append(payload)
        expected.append({"error": code})
    return inputs, expected


def verify(source: str, directory: Path, seed: int) -> dict[str, Any]:
    inputs, expected = cases(seed)
    actual = isolated(source, inputs)
    failures = [
        {"case": index, "input": inp, "expected": want, "actual": got}
        for index, (inp, want, got) in enumerate(
            zip(inputs, expected, actual, strict=True)
        )
        if want != got
    ]
    report = {
        "source_sha256": sha(source),
        "total": len(inputs),
        "passed": len(inputs) - len(failures),
        "seed": str(seed),
        "evaluator_version": "aya-sql-v1",
        "failures": failures,
    }
    save(directory / "report.json", report)
    return report
