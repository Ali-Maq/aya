"""Port a pinned Fireworks SQL capability through native Hermes and REA."""

import json
import secrets
import time
import traceback
from pathlib import Path
from typing import Any

from . import agents, intake, sql_client, sql_eval, sql_runtime
from .core import STATE, WORKER, Journal, gh, now, run, save, sha
from .evaluate import PYTHON_IMAGE
from .profiles import SOURCE_SHA, SOURCE_URL, SQL_DIRECTORY, SQL_REPOSITORY
from .rea import ReaClient


def read_worker(directory: Path, name: str) -> str:
    return run(
        [
            "nemohermes",
            WORKER,
            "exec",
            "--timeout",
            "20",
            "--no-stdin",
            "--",
            "cat",
            f"/sandbox/aya/{directory.name}/{name}",
        ],
        timeout=45,
        limit=60_000,
    )


def live_checks(source: str, directory: Path) -> dict[str, Any]:
    records = sql_runtime.records()
    checks = []
    questions = [
        (
            "Which three repositories have the most stars? Return repo and stars, ordered by stars descending, then repo ascending.",
            "SELECT repo, stars FROM repositories ORDER BY stars DESC, repo LIMIT 3",
        ),
        (
            "For each owner, what is the sum of stars? Return owner and total, ordered by owner.",
            "SELECT owner, SUM(stars) AS total FROM repositories GROUP BY owner ORDER BY owner",
        ),
        (
            "How many repositories are in this snapshot? Return one total column.",
            "SELECT COUNT(*) AS total FROM repositories",
        ),
        (
            "List repo and license for the Crusoe repositories only, ordered by repo.",
            "SELECT repo, license FROM repositories WHERE owner='crusoecloud' ORDER BY repo",
        ),
    ]
    api_key = sql_runtime.key()
    for question, query in questions:
        result = sql_client.ask(
            question,
            records,
            api_key,
            lambda payload: sql_eval.isolated(source, [payload], timeout=8)[0],
        )
        expected = sql_eval.oracle(records, query)
        checks.append(
            {
                "question": question,
                "passed": result["rows"] == expected["rows"],
                "expected": expected,
                "actual": result,
            }
        )
        save(
            directory / "live-checks.json",
            {
                "records": records,
                "checks": checks,
                "passed": sum(c["passed"] for c in checks),
                "total": len(questions),
            },
        )
    report = {
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "checks": checks,
        "records": records,
    }
    save(directory / "live-checks.json", report)
    if report["passed"] != report["total"]:
        raise RuntimeError("Real Crusoe query evaluation failed")
    return report


def build(number: int, directory: Path) -> None:
    from .pipeline import LOCK, state

    journal = Journal(directory)
    try:
        frozen = intake.snapshot(number, SQL_REPOSITORY)
        save(directory / "snapshot.json", frozen)
        journal.emit(
            "request_frozen",
            issue=frozen["issue"]["url"],
            target=SQL_REPOSITORY,
            contract_sha256=frozen["contract_sha256"],
            base_commit=frozen["target_base"],
        )
        state(directory, stage="Crusoe planning")
        plan = agents.plan(frozen["spec"], directory, journal)
        reference = STATE / "reference/fireworks-sql/sql_tools.py"
        if sha(reference.read_bytes()) != SOURCE_SHA:
            raise RuntimeError("Fireworks reference digest mismatch")
        state(directory, stage="REA source investigation")
        investigation = agents.worker(
            "Read the reverse-engineer-anything skill. Investigate the supplied Fireworks SQL source and capture its actual behavior through REA. "
            'This is source/runtime adaptation, NOT binary decompilation. Call the rea MCP capture_process_scenario tool with executable=/usr/local/bin/python3, arguments=["-B","/reference/fireworks-sql/probe.py"], working_directory=/tmp, timeout_ms=10000, limits={"output_bytes":30000}. '
            "These paths are on the REA server, not your local filesystem. The prepared probe executes selected unmodified upstream AST functions on a real SQLite snapshot; training and embeddings are excluded. "
            "The tool result is canonical evidence. Keep the returned evidence_id. Explain query result ordering, schema inspection, and the stricter read-only target boundary. "
            "Return JSON {observations:[strings],evidence_ids:[strings],limitations:[strings]}. Do not install packages or fetch other source. "
            "Pinned source URL: "
            + SOURCE_URL
            + "\nSource:\n"
            + reference.read_text()
            + "\nContract:\n"
            + json.dumps(frozen["spec"]),
            directory,
            journal,
            "investigation",
        )
        audit = json.loads((directory / "investigation-audit.json").read_text())
        if not any(
            "capture_process_scenario" in tool
            for session in audit["sessions"]
            for tool in session["tools"]
        ):
            raise RuntimeError(
                "Native Hermes did not capture the reference through REA"
            )
        evidence = ReaClient().call("get_evidence_bundle", {"detail": "complete"})
        claimed = set(investigation.get("evidence_ids", []))
        matched = []
        for record in evidence.get("result", {}).get("records", []):
            if (
                record.get("evidence_id") not in claimed
                or record.get("operation") != "capture_process_scenario"
            ):
                continue
            normalized = record.get("normalized_result") or {}
            if not isinstance(normalized, dict):
                continue
            scenario = normalized.get("manifest", {}).get("scenario", {})
            output = "".join(
                frame.get("data", "") for frame in normalized.get("frames", [])
            )
            if (
                record.get("evidence_id") in claimed
                and record.get("operation") == "capture_process_scenario"
                and scenario.get("executable") == "/usr/local/bin/python3"
                and scenario.get("arguments")
                == ["-B", "/reference/fireworks-sql/probe.py"]
                and normalized.get("exit", {}).get("code") == 0
                and SOURCE_SHA in output
            ):
                matched.append(record)
        if not matched:
            raise RuntimeError(
                "No claimed REA capture matches the pinned upstream source and successful probe"
            )
        save(
            directory / "evidence.json",
            {
                "investigation": investigation,
                "retained": matched,
                "reference_url": SOURCE_URL,
                "reference_sha256": SOURCE_SHA,
                "scope": "Selected upstream SQL functions; training and embeddings excluded",
            },
        )
        journal.emit(
            "reference_investigated",
            reference_sha256=SOURCE_SHA,
            evidence_ids=[r["evidence_id"] for r in matched],
        )
        feedback = ""
        source = ""
        for attempt in range(3):
            state(
                directory,
                stage="Hermes implementation" if attempt == 0 else "Hermes repair",
            )
            agents.worker(
                "Build query.py implementing execute(payload), tests/test_agent_query.py, and README.md in the current workspace. "
                "Read the test-driven-development skill. Write and run real unit tests using python3 -m unittest discover -s tests -v, with red/green steps. "
                "Use delegate_task once for a focused edge-case review; child must not delegate. No dependencies. "
                "query.py imports only sqlite3,json,re,typing,collections,math; no file IO, network, subprocess, dynamic execution or object internals. "
                "Use sqlite3.connect(':memory:') only. Initialize data, then query_only plus a SQLite authorizer to deny writes, PRAGMA, attach/detach, transactions and load_extension. Literal words in strings must remain legal. "
                "A progress handler must terminate expensive recursive queries with limit_exceeded. Reject >100 rows and >20 columns. Return errors exactly as contract defines. "
                "Tests may import unittest and query. README must explain the real Crusoe client, CRUSOE_API_KEY, run.py usage, dependencies (stdlib), read-only contract, Apache-2.0 attribution with pinned source URL, and excluded Fireworks training/embeddings. "
                "Return JSON {summary:string,tests_run:string}; actual files stay on disk.\nContract:"
                + json.dumps(frozen["spec"])
                + "\nReference:"
                + SOURCE_URL
                + "\nInvestigation:"
                + json.dumps(investigation)
                + "\nPlan:"
                + json.dumps(plan)
                + "\nDevelopment feedback:"
                + feedback,
                directory,
                journal,
                f"implementation-{attempt + 1}",
            )
            source = read_worker(directory, "query.py")
            sql_eval.validate(source)
            (directory / f"candidate-{attempt + 1}.py").write_text(source)
            (directory / "agent_tests.py").write_text(
                read_worker(directory, "tests/test_agent_query.py")
            )
            (directory / "README.md").write_text(read_worker(directory, "README.md"))
            state(directory, stage="Independent verification")
            report = sql_eval.verify(source, directory, secrets.randbits(64))
            save(directory / f"candidate-{attempt + 1}-report.json", report)
            journal.emit(
                "candidate_evaluated",
                attempt=attempt + 1,
                passed=report["passed"],
                total=report["total"],
                source_sha256=sha(source),
            )
            state(directory, passed=report["passed"], total=report["total"])
            if report["passed"] == report["total"]:
                break
            feedback = json.dumps(report["failures"])
        else:
            raise RuntimeError(
                "Candidate exhausted two repairs; integration is blocked"
            )
        holdout = sql_eval.verify(source, directory / "holdout", secrets.randbits(64))
        if holdout["passed"] != holdout["total"]:
            raise RuntimeError("Held-out evaluation failed")
        observed = json.loads(
            "".join(
                frame.get("data", "")
                for frame in matched[0]["normalized_result"]["frames"]
            ).strip()
        )
        reference_records = json.loads(
            (STATE / "reference/fireworks-sql/repositories.json").read_text()
        )
        reference_actual = sql_eval.isolated(
            source,
            [
                {"records": reference_records, "sql": item["sql"]}
                for item in observed["results"]
            ],
        )
        parity = {
            "total": len(reference_actual),
            "passed": sum(
                actual.get("rows") == expected["rows"]
                for actual, expected in zip(
                    reference_actual, observed["results"], strict=True
                )
            ),
            "reference": observed,
            "actual": reference_actual,
            "dataset_sha256": sha(json.dumps(reference_records, sort_keys=True)),
        }
        save(directory / "reference-parity.json", parity)
        if parity["passed"] != parity["total"]:
            raise RuntimeError(
                "Candidate differs from the captured upstream query results"
            )
        journal.emit(
            "reference_parity_passed", passed=parity["passed"], total=parity["total"]
        )
        (directory / "accepted.py").write_text(source)
        journal.emit(
            "acceptance_passed",
            checks=holdout["total"],
            source_sha256=sha(source),
            split="fresh held-out seed",
        )
        state(directory, stage="Live Crusoe verification")
        live = live_checks(source, directory)
        journal.emit(
            "live_calls_passed",
            passed=live["passed"],
            total=live["total"],
            provider="Crusoe",
            model=sql_client.MODEL,
        )
        intake.assert_current(frozen)
        state(directory, stage="GitHub delivery")
        checkout = directory / "checkout"
        run(
            [
                "git",
                "clone",
                "--quiet",
                f"https://github.com/{SQL_REPOSITORY}.git",
                str(checkout),
            ],
            timeout=90,
        )
        run(["git", "checkout", "--detach", frozen["target_base"]], cwd=checkout)
        branch = "aya/" + directory.name
        run(["git", "switch", "-c", branch], cwd=checkout)
        target = checkout / SQL_DIRECTORY
        (target / "query.py").write_text(source)
        (target / "tests/test_agent_query.py").write_text(
            (directory / "agent_tests.py").read_text()
        )
        (target / "README.md").write_text((directory / "README.md").read_text())
        save(
            target / "verification.json",
            {
                "run": directory.name,
                "issue": frozen["issue"]["url"],
                "contract_sha256": frozen["contract_sha256"],
                "reference_sha256": SOURCE_SHA,
                "reference_url": SOURCE_URL,
                "module_sha256": sha(source),
                "development": {k: v for k, v in report.items() if k != "failures"},
                "holdout": {k: v for k, v in holdout.items() if k != "failures"},
                "live_checks": live,
                "reference_parity": parity,
                "reference_evidence_ids": [r["evidence_id"] for r in matched],
                "reference_evidence": matched,
                "native_agents": [
                    json.loads(p.read_text())
                    for p in sorted(directory.glob("*-audit.json"))
                ],
                "inference": json.loads((directory / "crusoe.json").read_text()),
                "worker": WORKER,
            },
        )
        run(
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
                "-v",
                f"{target}:/app:ro",
                "-w",
                "/app",
                PYTHON_IMAGE,
                "python3",
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
            timeout=35,
            log=directory / "target-tests",
        )
        journal.emit(
            "target_tests_passed", command="python -m unittest discover -s tests -v"
        )
        run(["git", "add", SQL_DIRECTORY], cwd=checkout)
        run(
            [
                "git",
                "-c",
                "user.name=AYA",
                "-c",
                "user.email=aya@users.noreply.github.com",
                "commit",
                "-m",
                "Port Fireworks SQL tool workflow to a verified Crusoe cookbook",
            ],
            cwd=checkout,
        )
        commit = run(["git", "rev-parse", "HEAD"], cwd=checkout).strip()
        run(["git", "push", "-u", "origin", branch], cwd=checkout, timeout=90)
        body = directory / "pr.md"
        body.write_text(
            f"Adds a Crusoe repository analyst inspired by the pinned Fireworks SQL tools. Native Hermes investigated the actual upstream functions through REA, implemented the bounded SQL module, wrote unit tests, and delegated an edge-case review.\n\nIndependent checks: {report['passed']}/{report['total']} development and {holdout['passed']}/{holdout['total']} fresh held-out cases. Four live Crusoe questions were checked against an independent SQLite oracle over actual GitHub metadata. Agent and protected contract tests passed in a network-disabled container.\n\nIncludes source attribution, real provider call receipts, REA captures and module digest in `verification.json`. This ports the query workflow; it does not reproduce Fireworks GRPO training or embeddings.\n\nImplements #{number}. Request remains open for reruns.\n"
        )
        pr = run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                SQL_REPOSITORY,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                "Add verified Crusoe repository analyst cookbook",
                "--body-file",
                str(body),
            ],
            timeout=60,
        ).strip()
        state(directory, commit=commit, pr_url=pr, stage="GitHub CI")
        journal.emit("pull_request_created", url=pr, commit=commit)
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            checks = gh(f"repos/{SQL_REPOSITORY}/commits/{commit}/check-runs")[
                "check_runs"
            ]
            save(directory / "checks.json", checks)
            relevant = [c for c in checks if c["name"] == "aya-sql"]
            if relevant and all(c["status"] == "completed" for c in relevant):
                if not all(c["conclusion"] == "success" for c in relevant):
                    raise RuntimeError("GitHub CI rejected the delivered commit")
                break
            time.sleep(8)
        else:
            raise RuntimeError("GitHub CI deadline exceeded")
        intake.assert_current(frozen)
        journal.emit(
            "ci_passed", commit=commit, checks=[c["html_url"] for c in relevant]
        )
        save(
            STATE / "sql-deployment.json",
            {
                "run": directory.name,
                "commit": commit,
                "source_sha256": sha(source),
                "path": str(directory / "accepted.py"),
                "pr_url": pr,
                "at": now(),
            },
        )
        state(directory, status="complete", stage="Ready to try", completed_at=now())
        journal.emit(
            "module_activated",
            commit=commit,
            source_sha256=sha(source),
            product="http://localhost:3021/app/factory",
        )
    except Exception as exc:
        (directory / "error.log").write_text(traceback.format_exc())
        state(
            directory,
            status="failed",
            stage="Blocked",
            error=str(exc),
            completed_at=now(),
        )
        journal.emit("run_failed", error=str(exc))
    finally:
        LOCK.release()
