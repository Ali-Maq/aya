"""A frozen Spider subset with real databases and private execution oracles."""

import argparse
import hashlib
import json
import os
import sqlite3
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from . import public_db_executor

BENCHMARK_ID = "public-sql"
AYA_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = AYA_ROOT / "specs" / "spider-benchmark.json"
DEFAULT_CACHE = AYA_ROOT / ".state" / "public-sql"


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def _cache(cache_dir: Path | None) -> Path:
    return Path(cache_dir or os.environ.get("AYA_PUBLIC_SQL_CACHE", DEFAULT_CACHE))


def _verify(
    cache_dir: Path | None = None, *, require_preparation: bool = True
) -> tuple[Path, dict[str, Any]]:
    root = _cache(cache_dir)
    manifest = _manifest()
    for relative, expected in manifest["files"].items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or _digest(path) != expected:
            raise ValueError(f"Public SQL dataset missing or changed: {relative}")
    if require_preparation:
        receipt_path = root / "preparation.json"
        if not receipt_path.is_file():
            raise ValueError("Run public SQL prepare before evaluation")
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("case_manifest_sha256") != _digest(MANIFEST_PATH)
            or receipt.get("source") != manifest["source"]
            or receipt.get("verified_files") != manifest["files"]
        ):
            raise ValueError("Public SQL preparation receipt is stale")
    return root, manifest


def prepare(cache_dir: Path | None = None) -> dict[str, Any]:
    """Download one bounded official archive and extract only approved files."""
    root = _cache(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    source = manifest["source"]
    if source["url"] != (
        "https://huggingface.co/datasets/xlangai/spider/resolve/"
        "6232cc3fad6d54c62b3ba23a364083a98ff36a17/data/spider.zip"
    ):
        raise ValueError("Only the reviewed HTTPS dataset source is permitted")
    archive = root / "spider.zip"
    if not archive.is_file() or _digest(archive) != source["sha256"]:
        temporary = root / "spider.download"
        try:
            with (
                urllib.request.urlopen(source["url"], timeout=60) as response,  # noqa: S310 -- Exact HTTPS URL checked above.
                temporary.open("wb") as output,
            ):
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > source["bytes"]:
                        raise ValueError("Public dataset exceeds pinned download size")
                    output.write(chunk)
            if (
                temporary.stat().st_size != source["bytes"]
                or _digest(temporary) != source["sha256"]
            ):
                raise ValueError("Public dataset archive checksum mismatch")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for relative, member in manifest["archive_members"].items():
            info = bundle.getinfo(member)
            if info.file_size > 100_000_000:
                raise ValueError("Public dataset member exceeds extraction limit")
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = bundle.read(info)
            if hashlib.sha256(content).hexdigest() != manifest["files"][relative]:
                raise ValueError("Public dataset member checksum mismatch")
            destination.write_bytes(content)
            destination.chmod(0o644)
    _verify(root, require_preparation=False)
    receipt = {
        "benchmark": BENCHMARK_ID,
        "source": source,
        "case_manifest_sha256": _digest(MANIFEST_PATH),
        "verified_files": manifest["files"],
        "download_bytes": archive.stat().st_size,
    }
    (root / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def catalog(cache_dir: Path | None = None) -> dict[str, Any]:
    manifest = _manifest()
    try:
        _verify(cache_dir)
        ready = True
        error = None
    except ValueError as exc:
        ready = False
        error = str(exc)
    return {
        "id": BENCHMARK_ID,
        "benchmark": BENCHMARK_ID,
        "title": "Spider: joins across real databases",
        "ready": ready,
        "error": error,
        "source": manifest["source"]["url"],
        "provenance": manifest["source"],
        "development_count": len(manifest["splits"]["development"]),
        "heldout_count": len(manifest["splits"]["heldout"]),
        "development_questions": len(manifest["splits"]["development"]),
        "heldout_questions": len(manifest["splits"]["heldout"]),
        "dataset_source_sha256": manifest["source"]["sha256"],
        "case_manifest_sha256": _digest(MANIFEST_PATH),
        "executor_sha256": _digest(Path(public_db_executor.__file__)),
        "evaluator_sha256": _digest(Path(__file__)),
    }


def _cases(split: str, root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if split not in {"development", "heldout"}:
        raise ValueError("Split must be development or heldout")
    annotations = json.loads((root / "private" / "dev.json").read_text())
    cases = []
    for selected in manifest["splits"][split]:
        item = annotations[selected["source_index"]]
        if item["db_id"] != selected["db_id"]:
            raise ValueError("Frozen question identity mismatch")
        cases.append({**item, "id": selected["id"]})
    return cases


def _schema(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if len(tables) > 64 or sum(len(sql or "") for _, sql in tables) > 60000:
            raise ValueError("Public schema exceeds the context boundary")
        samples = {}
        for name, _ in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = connection.execute(f"SELECT * FROM {quoted} LIMIT 2")  # noqa: S608 -- SQLite identifier is quoted and escaped.
            if len(cursor.description) > 64:
                raise ValueError("Public table exceeds the column boundary")
            samples[name] = {
                "columns": [item[0] for item in cursor.description],
                "rows": [
                    [
                        value[:120]
                        if isinstance(value, str)
                        else value
                        if value is None or isinstance(value, (int, float))
                        else "<binary>"
                        for value in row
                    ]
                    for row in cursor.fetchall()
                ],
            }
        return {
            "schema": ";\n".join(statement for _, statement in tables if statement),
            "sample_rows": samples,
            "sample_rows_per_table": 2,
        }
    finally:
        connection.close()


def public_tasks(split: str, cache_dir: Path | None = None) -> dict[str, Any]:
    """Expose public question context, never gold SQL or expected result rows."""
    root, manifest = _verify(cache_dir)
    tasks = _cases(split, root, manifest)
    databases = {
        name: _schema(root / "databases" / f"{name}.sqlite")
        for name in sorted({item["db_id"] for item in tasks})
    }
    return {
        "benchmark": BENCHMARK_ID,
        "split": split,
        "provenance": {
            key: manifest["source"][key]
            for key in ("repository", "revision", "license")
        },
        "case_manifest_sha256": _digest(MANIFEST_PATH),
        "databases": databases,
        "questions": [
            {"id": item["id"], "db_id": item["db_id"], "question": item["question"]}
            for item in tasks
        ],
    }


def _same_rows(expected: dict[str, Any], actual: dict[str, Any], ordered: bool) -> bool:
    if "error" in actual or not isinstance(actual.get("rows"), list):
        return False
    if len(expected["columns"]) != len(actual.get("columns", [])):
        return False
    if ordered:
        return expected["rows"] == actual["rows"]

    # Preserve duplicate rows. Column aliases do not affect execution equivalence.
    def row_key(row: list[Any]) -> tuple[Any, ...]:
        return tuple(
            ("blob", value["blob_hex"]) if isinstance(value, dict) else value
            for value in row
        )

    return Counter(map(row_key, expected["rows"])) == Counter(
        map(row_key, actual["rows"])
    )


def evaluate(answers: Any, split: str, cache_dir: Path | None = None) -> dict[str, Any]:
    """Score generated SQL against private Spider SQL in isolated SQLite."""
    root, manifest = _verify(cache_dir)
    tasks = _cases(split, root, manifest)
    ids = {item["id"] for item in tasks}
    protocol_valid = isinstance(answers, dict) and set(answers) == ids
    answers = answers if protocol_valid else {}
    requests = []
    pending = []
    failures = []
    success = {item["id"]: False for item in tasks}
    for task in tasks:
        answer = answers.get(task["id"])
        if (
            not isinstance(answer, dict)
            or set(answer) != {"sql"}
            or not isinstance(answer["sql"], str)
            or not 0 < len(answer["sql"]) <= 20000
        ):
            failures.append({"id": task["id"], "reason": "sql_answer_required"})
            continue
        requests.extend(
            [
                {"db_id": task["db_id"], "sql": task["query"]},
                {"db_id": task["db_id"], "sql": answer["sql"]},
            ]
        )
        pending.append(task)
    outputs = (
        public_db_executor.execute_queries(root / "databases", requests)
        if requests
        else []
    )
    for index, task in enumerate(pending):
        expected, actual = outputs[index * 2 : index * 2 + 2]
        if "error" in expected:
            raise RuntimeError(f"Pinned benchmark oracle failed for {task['id']}")
        passed = _same_rows(expected, actual, bool(task["sql"]["orderBy"]))
        success[task["id"]] = passed
        if not passed:
            failures.append(
                {"id": task["id"], "reason": actual.get("error", "result_mismatch")}
            )
    identity = catalog(root)
    return {
        "benchmark": BENCHMARK_ID,
        "split": split,
        "passed": sum(success.values()),
        "total": len(tasks),
        "task_passed": sum(success.values()),
        "task_total": len(tasks),
        "protocol_valid": protocol_valid,
        "dataset_source_sha256": identity["dataset_source_sha256"],
        "case_manifest_sha256": identity["case_manifest_sha256"],
        "dataset_sha256": identity["dataset_source_sha256"],
        "case_sha256": identity["case_manifest_sha256"],
        "executor_source_sha256": identity["executor_sha256"],
        "evaluator_sha256": identity["evaluator_sha256"],
        "by_question": [
            {"id": item["id"], "passed": int(success[item["id"]]), "total": 1}
            for item in tasks
        ],
        "failures": failures,
        "metric": "single-database execution agreement; not Spider official test-suite accuracy",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "catalog", "public-tasks"])
    parser.add_argument(
        "--split", choices=["development", "heldout"], default="development"
    )
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    result = (
        prepare(args.cache_dir)
        if args.command == "prepare"
        else catalog(args.cache_dir)
        if args.command == "catalog"
        else public_tasks(args.split, args.cache_dir)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
