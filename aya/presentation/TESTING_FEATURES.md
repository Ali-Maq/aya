# Testing a feature request

The feature spec needs an executable contract before a build can earn an accepted status.
The contract defines the input, output, supported behavior, errors, and target paths.

## Test the current SQL example

1. Open [AYA](http://localhost:3021/app/factory).
2. Select the reviewed Fireworks SQL example.
3. Open its GitHub issue and inspect `specs/crusoe-repository-analyst.json`.
4. Start the build, or select completed run `492e2ca7851347f5`.
5. Inspect the reference capture and first candidate report.
6. Find the whitespace-only query. Its expected result is `invalid_request`.
7. Check the repair, fresh-seed result, and deployed commit.
8. Open the [generated PR](https://github.com/Ali-Maq/crusoe-developer-hub/pull/2) and its Actions checks.
9. Ask a new question in AYA. Inspect its SQL, result table, and Crusoe receipt.

The completed run passed 118 independent checks, then 118 checks with a fresh seed.
It also passed three upstream comparisons, four real Crusoe questions, and 54 target tests.
The first candidate passed 117 independent checks. Keep that failure in the demo.

## Reproduce the target suite

Use a new directory to avoid changing another checkout. Check out the actual PR before running tests.

```sh
gh repo clone Ali-Maq/crusoe-developer-hub aya-crusoe-review
cd aya-crusoe-review
gh pr checkout 2
cd examples/cookbooks/repository-analyst
python3 -m unittest discover -s tests -v
```

To make a real provider call, set `CRUSOE_API_KEY` through your normal secret mechanism, then run:

```sh
python3 run.py "Which three repositories have the most stars?"
```

This command fetches GitHub metadata and calls Crusoe. Its output contains the actual SQL and response receipts.
The standalone command runs locally. The AYA browser path executes the accepted module in a restricted container.

## Acceptance layers

| Layer | Who controls it | What it establishes |
| --- | --- | --- |
| Reference capture | REA and the frozen source | The observed upstream behavior and artifact identity |
| Agent tests | Native Hermes | The implementation's own expected behavior |
| Independent cases | Factory evaluator | Behavior the agent tests may miss |
| Fresh-seed cases | Factory evaluator | Generalization beyond returned development counterexamples |
| Target suite | Target repository | Integration with the declared interface |
| GitHub Actions | Target CI | The delivered commit passes the target checks |
| Live product call | Product runtime | The accepted module works through the real provider path |

Deterministic inputs and test databases are test fixtures. They do not replace live provider calls.
The demo labels those two evidence types separately.

## Test the public SQL MASS workflow

1. Open **Agent improvement** and select **Spider: joins across real databases**.
2. Read the [public benchmark contract](../specs/mass-public-sql.json) and [selection manifest](../specs/spider-benchmark.json). The current demo uses 12 development questions across six databases and six held-out questions across three other databases.
3. Select a completed experiment, or start one real experiment. The Run button also authorizes its bounded training stage: one epoch using ten independently passing training answers and two fixed validation answers, if that gate passes.
4. Inspect the bare-model baseline, native Hermes initial workflow, and actual MASS RHI proposal. Do not infer their scores from the oracle self-check.
5. Open each native trace and Langfuse receipt. Active traces can have tool events before usage counters persist; **Model usage pending** is not a measured zero.
6. Inspect the protected development report and selection decision. Freeze the selected workflow before evaluating the six held-out questions.
7. Check stored-trajectory selection and the actual training result. Insufficient verified rows must finish without submitting a job. A succeeded training job is not a serving or quality result.

The public worker input comes from `public_sql_benchmark.public_tasks("development")`: question IDs and text, CREATE TABLE schemas, and at most two sample rows per table. It has no seed parameter and contains no expected SQL. The answer is `queries.json`, mapping each supplied ID to exactly one `sql` string.

The controller runs submitted SQL and the trusted reference through `public_db_executor.py` in restricted containers against the same checksum-verified database. This is a separate executor from the accepted single-table repository component. Each question has one database execution comparison: **12 development checks, then six held-out checks**. There are no three-seed or refusal tasks in this public subset.

Actual MASS RHI reads an allowlisted development bundle, proposes a workflow, and compares measured episode evidence. The independent selection gate still requires a strict development improvement; ties retain the initial workflow. Report a perfect baseline as a ceiling, not as an improvement.

### Earlier repository fixture

The preserved fixture experiment `76f46a90fc23427d` uses `sql_benchmark.public_tasks("development", seed)`, the fixed accepted repository executor, and 12 questions per split across three datasets. It reports 36 checks and 12 task outcomes per split. Each task passes only if all three checks pass. Its baseline, v0, and v1 all passed 36/36 development checks; retained v0 passed 36/36 held-out checks. These are not Spider scores.

See [BENCHMARK.md](BENCHMARK.md) and [PUBLIC_SQL.md](../PUBLIC_SQL.md) for exact semantics and limitations.

### Execution boundary

Native Hermes episodes receive fresh workspaces within **one shared OpenShell worker filesystem**. Cross-run file isolation is not enforced. The public v0 trace read an unrelated earlier fixture file from a sibling workspace; no current Spider reference SQL was observed. The SQL execution containers have a separate restricted boundary. Do not describe the whole prototype as a fresh isolated sandbox per job.

## Failure checks for the demonstration

- Submit a modified spec. It should remain a proposal until its contract has a reviewed evaluator.
- Submit an unsupported target repository. The factory should reject it before starting a worker.
- Inspect a failed run. Its failure should remain visible after a repair or resume.
- Request a SQL write. The accepted module should return `read_only`.
- Open factory controls without an admin session. Access should fail.
- Compare the deployed source hash with the accepted module. A mismatch must block execution.

## Observable model trace

Show tool names, timestamps, tool arguments, redacted outputs, tests, code changes, and child-agent lineage.
Show concise progress summaries when the agent exposes them.
Do not label hidden chain-of-thought as a required audit artifact. The evidence is the action and its observable result.

## Controlled comparison

Use the same feature tasks, reference access, model, and budget for both conditions.
One condition uses the normal coding workflow. The other uses AYA's independent acceptance gate.
Keep held-out tests unchanged and hidden from both builders. Report correctness, defects, elapsed time, and API usage.
The completed one-shot module comparison uses unequal budgets. It is evidence for one case, not that controlled experiment.
The NL workflow benchmark is a separate experiment. Do not compare the public 12/6 scores or the earlier fixture’s 36-check scores directly with component checks out of 118.
