import ast
import hashlib
import json
import pathlib
import sqlite3
import typing

root = pathlib.Path(__file__).parent
source = (root / "sql_tools.py").read_text()
reward = ast.parse((root / "sql_reward.py").read_text())
RESULT_MARKER = next(
    ast.literal_eval(n.value)
    for n in reward.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "RESULT_MARKER" for t in n.targets)
)
DB_ROOT = pathlib.Path("/tmp/aya-source-probe")  # noqa: S108 — isolated REA tmpfs, no host mount
MAX_RESULT_ROWS = 200
p = DB_ROOT / "github"
p.mkdir(parents=True, exist_ok=True)
db = p / "github.sqlite"
c = sqlite3.connect(db)
c.execute("DROP TABLE IF EXISTS repositories")
c.execute(
    "CREATE TABLE repositories(repo TEXT, owner TEXT, stars INTEGER, forks INTEGER, issues INTEGER, license TEXT, description TEXT, url TEXT)"
)
rows = json.loads((root / "repositories.json").read_text())
c.executemany(
    "INSERT INTO repositories VALUES(?,?,?,?,?,?,?,?)",
    [
        tuple(
            r[k]
            for k in [
                "repo",
                "owner",
                "stars",
                "forks",
                "issues",
                "license",
                "description",
                "url",
            ]
        )
        for r in rows
    ],
)
c.commit()
c.close()
functions = [
    n
    for n in ast.parse(source).body
    if isinstance(n, ast.FunctionDef)
    and n.name
    in {
        "_db_path",
        "describe_database",
        "get_database_schema",
        "run_sql_against_database",
    }
]
ns = dict(
    globals(), Path=pathlib.Path, Any=typing.Any, List=typing.List, Tuple=typing.Tuple
)
exec(  # noqa: S102 — pinned functions execute only in the network-isolated REA container
    compile(
        ast.Module(body=functions, type_ignores=[]),
        "pinned-upstream-sql-functions",
        "exec",
    ),
    ns,
)
schema = ns["get_database_schema"]("github")
queries = [
    "SELECT repo, stars FROM repositories ORDER BY stars DESC, repo LIMIT 3",
    "SELECT owner, SUM(stars) AS stars FROM repositories GROUP BY owner ORDER BY owner",
    "SELECT COUNT(*) AS total FROM repositories",
]
results = [
    {"sql": q, "rows": ns["run_sql_against_database"](q, "github")[1]} for q in queries
]
print(
    json.dumps(
        {
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "schema_observed": bool(schema),
            "results": results,
            "scope": "Executed selected unmodified upstream AST functions; training and embeddings excluded",
        },
        ensure_ascii=True,
    )
)
