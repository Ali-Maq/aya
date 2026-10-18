"""Independent reference comparisons; expected answers stay outside workers."""

import ast
import json
import random
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .core import run, save, sha

ORACLE_IMAGE = "ghcr.io/nvidia/nemoclaw/hermes-sandbox@sha256:09cc86372e224afaa4c5308af4157dc4b2d0315d4f872584b3e2fdd32180f74e"
PYTHON_IMAGE = (
    "python@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203"
)
EXPECTED_JQ = "9d139c59dea37367a8a8f59bf923ca04f2227313a3bacfeabf1cd775c1719bb0"
EXPECTED_LIB = "0860ff6f0b18028f50e275e95ce56de0d30f6c2387a6679eed292d81facb6bbe"
ORACLE = """. as $p | ($p.columns | map(.label)) as $h |
[$p.records[] | . as $r | [$p.columns[] | . as $c | ($r | getpath($c.path)) as $v |
if ($c | has("fallback")) and (($v == null) or (($c.fallback_mode // "jq") == "jq" and $v == false)) then $c.fallback else $v end]] as $r |
{columns:$h,rows:$r,csv:(([$h]+$r | map(@csv) | join("\n"))+"\n")}"""
RUNNER = """import json,sys
p=json.load(sys.stdin)
n={"__name__":"recipe"}
exec(compile(p["source"],"recipe.py","exec"),n)
result=[]
for request in p["requests"]:
 try: result.append(n["export_recipe"](request))
 except Exception as e: result.append({"exception":type(e).__name__})
print(json.dumps(result,allow_nan=False,ensure_ascii=True))
"""


def validate_source(source: str) -> None:
    if not isinstance(source, str) or len(source.encode()) > 50_000:
        raise ValueError("Component source exceeds the allowed size")
    tree = ast.parse(source)
    allowed = {"json", "csv", "io", "math", "typing", "collections", "re"}
    blocked = {
        "eval",
        "exec",
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
        isinstance(node, ast.FunctionDef) and node.name == "export_recipe"
        for node in tree.body
    ):
        raise ValueError("Missing export_recipe function")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] not in allowed for alias in node.names
        ):
            raise ValueError("Component imports an unsupported module")
        if isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or "").split(".")[0] not in allowed
        ):
            raise ValueError("Component imports an unsupported module")
        if isinstance(node, ast.Name) and node.id in blocked:
            raise ValueError(f"Component uses prohibited operation: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Component uses dynamic object internals")


def isolated(source: str, requests: list[Any], timeout: int = 25) -> list[Any]:
    validate_source(source)
    name = "aya-eval-" + uuid.uuid4().hex[:12]
    image = run(
        ["docker", "image", "inspect", PYTHON_IMAGE, "--format", "{{.Id}}"], timeout=10
    ).strip()
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
                "--pids-limit",
                "32",
                "--memory",
                "128m",
                "--cpus",
                "1",
                "--user",
                "65534:65534",
                "-i",
                image,
                "python3",
                "-I",
                "-B",
                "-c",
                RUNNER,
            ],
            data=json.dumps({"source": source, "requests": requests}),
            timeout=timeout,
            limit=8_000_000,
        )
        values = json.loads(output)
        if not isinstance(values, list) or len(values) != len(requests):
            raise RuntimeError("Invalid component result envelope")
        return values
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


def reference(requests: list[dict[str, Any]]) -> list[Any]:
    hashes = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "sha256sum",
            ORACLE_IMAGE,
            "/usr/bin/jq",
            "/usr/lib/aarch64-linux-gnu/libjq.so.1.0.4",
        ]
    )
    if EXPECTED_JQ not in hashes or EXPECTED_LIB not in hashes:
        raise RuntimeError("Reference binary identity changed")
    output = run(
        [
            "docker",
            "run",
            "--rm",
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
            "--user",
            "65534:65534",
            "-i",
            "--entrypoint",
            "jq",
            ORACLE_IMAGE,
            "-c",
            ORACLE,
        ],
        data="\n".join(json.dumps(r) for r in requests),
        timeout=40,
    )
    results = [json.loads(line) for line in output.splitlines()]
    if len(results) != len(requests):
        raise RuntimeError("Reference did not answer every request")
    return results


def cases(seed: int) -> tuple[list[Any], list[dict[str, str]]]:
    rng = random.Random(seed)
    scalars: list[Any] = [
        None,
        False,
        True,
        0,
        -1,
        9007199254740991,
        "",
        "a,b",
        'a"b',
        "a\nb",
        "a\rb",
        "é東京",
        "a\x00b",
    ]
    valid: list[Any] = []
    for i in range(180):
        records = [
            {
                "name": rng.choice(scalars),
                "nested": {"x": rng.choice(scalars)},
                "list": scalars[:3],
            }
            for _ in range(rng.randrange(0, 7))
        ]
        columns = [
            {"label": "Name", "path": ["name"]},
            {
                "label": "Selected",
                "path": ["nested", "x"],
                "fallback": rng.choice(scalars),
                "fallback_mode": "null" if i % 2 else "jq",
            },
            {"label": "Missing", "path": ["absent", "child"], "fallback": "missing"},
            {"label": 'Array,"\n', "path": ["list", i % 5]},
        ]
        valid.append({"records": records, "columns": columns})
    valid += [
        {
            "records": [{"x": value}],
            "columns": [{"label": "x", "path": ["x"], "fallback": "F"}],
        }
        for value in scalars
    ]
    base = {"records": [{}], "columns": [{"label": "x", "path": ["x"]}]}
    invalid: list[tuple[Any, str]] = [
        (None, "invalid_recipe"),
        ({}, "invalid_recipe"),
        ({**base, "records": [1]}, "invalid_recipe"),
        ({**base, "columns": []}, "invalid_recipe"),
        ({**base, "columns": [{"label": "x", "path": [-1]}]}, "invalid_recipe"),
        ({**base, "columns": [{"label": "x", "path": [True]}]}, "invalid_recipe"),
        (
            {
                **base,
                "columns": [{"label": "x", "path": ["x"], "fallback_mode": "truthy"}],
            },
            "invalid_recipe",
        ),
        ({**base, "records": [{"x": 1.5}]}, "unsupported_number"),
        ({**base, "records": [{"x": 9007199254740992}]}, "unsupported_number"),
        ({**base, "records": [{"x": {}}]}, "non_scalar"),
        ({**base, "records": [{"x": []}]}, "non_scalar"),
        (
            {**base, "columns": [{"label": "x", "path": ["x"], "fallback": []}]},
            "non_scalar",
        ),
        (
            {"records": [{"x": 1}], "columns": [{"label": "x", "path": ["x", "a"]}]},
            "path_type",
        ),
        (
            {"records": [{"x": []}], "columns": [{"label": "x", "path": ["x", "a"]}]},
            "path_type",
        ),
        ({**base, "records": [{}] * 10001}, "limit_exceeded"),
        ({**base, "columns": base["columns"] * 33}, "limit_exceeded"),
        ({**base, "records": [{"x": "x" * 1048576}]}, "limit_exceeded"),
    ]
    return valid + [pair[0] for pair in invalid], [
        {"error": pair[1]} for pair in invalid
    ]


def verify(source: str, directory: Path, seed: int) -> dict[str, Any]:
    validate_source(source)
    inputs, errors = cases(seed)
    expected = reference(inputs[: len(inputs) - len(errors)]) + errors
    actual = isolated(source, inputs)
    failures = [
        {"case": i, "input": request, "expected": want, "actual": got}
        for i, (request, want, got) in enumerate(
            zip(inputs, expected, actual, strict=True)
        )
        if got != want
    ]
    report = {
        "source_sha256": sha(source),
        "total": len(inputs),
        "passed": len(inputs) - len(failures),
        "reference_sha256": EXPECTED_JQ,
        "library_sha256": EXPECTED_LIB,
        "evaluator_version": "aya-recipe-v1",
        "seed": str(seed),
        "failures": failures[:8],
    }
    save(directory / "report.json", report)
    return report
