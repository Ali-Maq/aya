"""A bounded GitHub-to-pull-request feature build."""

import json
import secrets
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from . import agents, intake
from .core import REPOSITORY, STATE, WORKER, Journal, events, gh, now, run, save, sha
from .evaluate import EXPECTED_LIB, PYTHON_IMAGE, validate_source, verify
from .rea import ReaClient

LOCK = threading.Lock()
RUNS = STATE / "runs"
RUNS.mkdir(exist_ok=True)


def state(directory: Path, **updates: Any) -> dict[str, Any]:
    path = directory / "state.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update(updates)
    save(path, current)
    return current


def list_runs() -> list[dict[str, Any]]:
    return sorted(
        [json.loads(p.read_text()) for p in RUNS.glob("*/state.json")],
        key=lambda row: row["started_at"],
        reverse=True,
    )


def detail(identity: str) -> dict[str, Any]:
    directory = RUNS / identity
    if not (directory / "state.json").exists():
        raise FileNotFoundError("Run not found")

    def read(name: str) -> Any:
        path = directory / name
        return json.loads(path.read_text()) if path.exists() else None

    source = directory / "accepted.py"
    return {
        "run": read("state.json"),
        "events": events(directory),
        "snapshot": read("snapshot.json"),
        "plan": read("plan.json"),
        "evidence": read("evidence.json"),
        "report": {
            "latest": read("report.json"),
            "attempts": [
                json.loads(path.read_text())
                for path in sorted(directory.glob("candidate-*-report.json"))
            ],
            "holdout": read("holdout/report.json"),
        },
        "live_checks": read("live-checks.json"),
        "checks": read("checks.json"),
        "source": source.read_text() if source.exists() else None,
        "audits": [
            json.loads(p.read_text()) for p in sorted(directory.glob("*-audit.json"))
        ],
    }


def start(number: int, actor: str, repository: str = REPOSITORY) -> dict[str, Any]:
    from .profiles import for_repository
    from .sql_pipeline import build as sql_build

    profile = for_repository(repository)
    if not LOCK.acquire(blocking=False):
        raise RuntimeError("One feature job is already using the dedicated worker")
    identity = uuid.uuid4().hex[:16]
    directory = RUNS / identity
    directory.mkdir()
    value = state(
        directory,
        id=identity,
        status="running",
        stage="GitHub intake",
        issue_number=number,
        target_repository=repository,
        profile=profile["id"],
        started_at=now(),
        actor=actor,
        sandbox=WORKER,
    )
    threading.Thread(
        target=sql_build if profile["id"] == "crusoe-repository-analyst" else build,
        args=(number, directory),
        daemon=True,
    ).start()
    return value


def build(number: int, directory: Path) -> None:
    journal = Journal(directory)
    try:
        frozen = intake.snapshot(number)
        save(directory / "snapshot.json", frozen)
        journal.emit(
            "request_frozen",
            issue=frozen["issue"]["url"],
            target=REPOSITORY,
            contract_sha256=frozen["contract_sha256"],
            base_commit=frozen["target_base"],
        )
        state(directory, stage="Crusoe planning")
        plan = agents.plan(frozen["spec"], directory, journal)
        state(directory, stage="REA binary investigation")
        investigation = agents.worker(
            "Read the reverse-engineer-anything skill. Investigate the installed jq shared library through the rea MCP tools. "
            "The MCP server's file is /reference/libjq.so (server-side container path, not your local filesystem). "
            "Call open_binary with provider_id ghidra, then search_procedures and procedure_pseudo_code for jv_getpath. "
            "If a binary is already open, inspect binary_session and use that matching file. "
            "Keep investigation focused; do not fetch source or install packages. Do not close the binary until you have retained its evidence. "
            "Use the terminal to run installed jq probes that distinguish false, null, zero, empty string and CSV escaping. "
            "Return JSON {observations:[strings],evidence_ids:[strings],limitations:[strings]}. "
            "Explain what decompilation establishes versus what probes establish. Contract: "
            + json.dumps(frozen["spec"]),
            directory,
            journal,
            "investigation",
        )
        audit = json.loads((directory / "investigation-audit.json").read_text())
        tool_names = [
            tool for session in audit["sessions"] for tool in session["tools"]
        ]
        if not any(
            "procedure_pseudo_code" in tool or "analyze_function" in tool
            for tool in tool_names
        ):
            raise RuntimeError("No native Hermes decompilation tool call was observed")
        evidence = ReaClient().call("get_evidence_bundle", {"detail": "complete"})
        claimed = set(investigation.get("evidence_ids", []))
        records = evidence.get("result", {}).get("records", [])
        matched = [
            record
            for record in records
            if record.get("evidence_id") in claimed
            and record.get("operation") == "procedure_pseudo_code"
            and record.get("subject", {}).get("digest", {}).get("sha256")
            == EXPECTED_LIB
            and record.get("raw_result", {}).get("value")
        ]
        if not matched:
            raise RuntimeError(
                "No claimed REA decompilation evidence matches the pinned library"
            )
        save(
            directory / "evidence.json",
            {
                "investigation": investigation,
                "retained": evidence,
                "boundary": "network-none Docker container; read-only reference; no host home or credentials",
            },
        )
        journal.emit(
            "binary_investigated",
            reference_sha256=EXPECTED_LIB,
            evidence_ids=investigation.get("evidence_ids", []),
        )
        state(directory, stage="Hermes implementation")
        feedback = ""
        source = ""
        for attempt in range(3):
            role = f"implementation-{attempt + 1}"
            agents.worker(
                "Implement recipe.py with export_recipe(payload) and tests/test_agent_recipe.py. "
                "Read the installed test-driven-development skill. Write and run tests in red/green steps with python3 -m unittest discover -s tests -v. "
                "Use delegate_task once for a focused independent edge-case review; the child must not delegate. "
                "Create files in the current workspace; no dependencies to install. Allowed imports: json,csv,io,math,typing,collections,re. "
                "No file IO, network, subprocess, eval, exec, compile, getattr or object internals in recipe.py. "
                "Tests may import unittest and recipe. The target module must fully validate the declared contract. "
                "Return JSON {summary:string,tests_run:string}; leave the actual files on disk. "
                "Contract: "
                + json.dumps(frozen["spec"])
                + "\nInvestigation: "
                + json.dumps(investigation)
                + "\nPlan: "
                + json.dumps(plan)
                + "\nDevelopment feedback: "
                + feedback,
                directory,
                journal,
                role,
            )
            source = run(
                [
                    "nemohermes",
                    WORKER,
                    "exec",
                    "--timeout",
                    "20",
                    "--no-stdin",
                    "--",
                    "cat",
                    f"/sandbox/aya/{directory.name}/recipe.py",
                ],
                timeout=45,
                limit=60_000,
            )
            tests = run(
                [
                    "nemohermes",
                    WORKER,
                    "exec",
                    "--timeout",
                    "20",
                    "--no-stdin",
                    "--",
                    "cat",
                    f"/sandbox/aya/{directory.name}/tests/test_agent_recipe.py",
                ],
                timeout=45,
                limit=60_000,
            )
            validate_source(source)
            (directory / f"candidate-{attempt + 1}.py").write_text(source)
            (directory / "agent_tests.py").write_text(tests)
            (directory / f"candidate-{attempt + 1}-tests.py").write_text(tests)
            state(directory, stage="Independent verification")
            report = verify(source, directory, secrets.randbits(64))
            save(directory / f"candidate-{attempt + 1}-report.json", report)
            journal.emit(
                "candidate_evaluated",
                attempt=attempt + 1,
                passed=report["passed"],
                total=report["total"],
                source_sha256=report["source_sha256"],
            )
            state(directory, passed=report["passed"], total=report["total"])
            if report["passed"] == report["total"]:
                break
            feedback = json.dumps(report["failures"])
            state(directory, stage="Hermes repair")
        else:
            raise RuntimeError(
                "Candidate exhausted two repairs; integration is blocked"
            )
        # A fresh split is evaluated after development feedback ends.
        final_report = verify(source, directory / "holdout", secrets.randbits(64))
        if final_report["passed"] != final_report["total"]:
            raise RuntimeError("Held-out evaluation failed; integration is blocked")
        (directory / "accepted.py").write_text(source)
        journal.emit(
            "acceptance_passed",
            checks=final_report["total"],
            source_sha256=sha(source),
            split="fresh held-out seed",
        )
        intake.assert_current(frozen)
        state(directory, stage="GitHub delivery")
        checkout = directory / "checkout"
        run(
            [
                "git",
                "clone",
                "--quiet",
                f"https://github.com/{REPOSITORY}.git",
                str(checkout),
            ],
            timeout=90,
        )
        run(["git", "checkout", "--detach", frozen["target_base"]], cwd=checkout)
        branch = "aya/" + directory.name
        run(["git", "switch", "-c", branch], cwd=checkout)
        (checkout / "recipe.py").write_text(source)
        (checkout / "tests/test_agent_recipe.py").write_text(
            (directory / "agent_tests.py").read_text()
        )
        save(
            checkout / "verification.json",
            {
                "run": directory.name,
                "issue": frozen["issue"]["url"],
                "contract_sha256": frozen["contract_sha256"],
                "reference_sha256": EXPECTED_LIB,
                "module_sha256": sha(source),
                "development": {k: v for k, v in report.items() if k != "failures"},
                "holdout": {k: v for k, v in final_report.items() if k != "failures"},
                "evidence_ids": investigation.get("evidence_ids", []),
                "reference_evidence": matched,
                "native_agents": [
                    json.loads(path.read_text())
                    for path in sorted(directory.glob("*-audit.json"))
                ],
                "inference": json.loads((directory / "crusoe.json").read_text()),
                "worker": WORKER,
            },
        )
        # Agent tests execute inside a separate container with no credentials or network.
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
                f"{checkout}:/app:ro",
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
        run(
            [
                "git",
                "add",
                "recipe.py",
                "tests/test_agent_recipe.py",
                "verification.json",
            ],
            cwd=checkout,
        )
        run(
            [
                "git",
                "-c",
                "user.name=AYA",
                "-c",
                "user.email=aya@users.noreply.github.com",
                "commit",
                "-m",
                "Recover bounded JSON export recipes from jq behavior",
            ],
            cwd=checkout,
        )
        commit = run(["git", "rev-parse", "HEAD"], cwd=checkout).strip()
        run(["git", "push", "-u", "origin", branch], cwd=checkout, timeout=90)
        body = directory / "pr.md"
        body.write_text(
            f"Adds the bounded JSON export component for Open WebUI. Hermes inspected the pinned libjq binary through REA and wrote the module and its tests.\n\nIndependent verification: {report['passed']}/{report['total']} development cases and {final_report['passed']}/{final_report['total']} cases from a fresh held-out seed. Agent tests and integration contract tests also passed in a container without network access.\n\nModule SHA-256: `{sha(source)}`. Full local run: `{directory.name}`. See `verification.json` for source bindings.\n\nImplements #{number}. The request stays open for demo reruns.\n"
        )
        pr = run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                "Add verified JSON export recipes for Open WebUI",
                "--body-file",
                str(body),
            ],
            timeout=60,
        ).strip()
        state(directory, commit=commit, pr_url=pr, stage="GitHub CI")
        journal.emit("pull_request_created", url=pr, commit=commit)
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            checks = gh(f"repos/{REPOSITORY}/commits/{commit}/check-runs")["check_runs"]
            save(directory / "checks.json", checks)
            relevant = [check for check in checks if check["name"] == "contract"]
            if relevant and all(check["status"] == "completed" for check in relevant):
                if not all(check["conclusion"] == "success" for check in relevant):
                    raise RuntimeError("GitHub CI rejected the delivered commit")
                break
            time.sleep(8)
        else:
            raise RuntimeError(
                "GitHub CI did not complete within the delivery deadline"
            )
        intake.assert_current(frozen)
        journal.emit(
            "ci_passed", commit=commit, checks=[check["html_url"] for check in relevant]
        )
        save(
            STATE / "deployment.json",
            {
                "run": directory.name,
                "commit": commit,
                "source_sha256": sha(source),
                "path": str(directory / "accepted.py"),
                "pr_url": pr,
                "at": now(),
            },
        )
        state(
            directory,
            status="complete",
            stage="Available in Open WebUI",
            completed_at=now(),
        )
        journal.emit(
            "module_activated",
            commit=commit,
            source_sha256=sha(source),
            product="http://localhost:3032",
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
