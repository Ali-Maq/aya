# AYA Factory

**Verified against:** `7f12bab162` (2026-10-17)
**Domain:** aya-factory
**Edition:** CE extension.
**Owns:** `aya/`, `web/src/app/app/factory/`, `web/src/app/api/aya/`.
The verification includes the AYA working changes on this base.

## 1. What the user experiences

An administrator opens the Factory view in Onyx. Two peer tabs separate component recovery from agent improvement. The reverse-engineering tab shows GitHub requests, delivery evidence, and live component use. The agent-improvement tab shows bounded MASS text-to-SQL experiments, public agent actions, strategy changes, verified Langfuse records, and Crusoe training status. Tab selection persists in the URL.
Each request names a target repository. Onyx is the factory interface.

## 2. Surfaces

The page uses the authenticated proxy in `web/src/app/api/aya/[...path]/route.ts`.
The host controller exposes request creation, runs, run details, SQL deployment identity, and a real Crusoe query endpoint. GET `/mass` and `/mass/{id}` expose experiments. GET `/mass/catalog` exposes verified benchmark readiness. GET `/mass/trajectories` exposes the latest verified trajectory selection. POST `/mass` accepts a benchmark identity and starts a background experiment.
The token names and local ports are defined in `aya/aya_factory/server.py:Handler`.

## 3. Data model

`aya/aya_factory/core.py:save` writes atomic JSON receipts. `Journal.emit` appends durable events.
Each run retains a frozen issue, contract, source hash, native agent audit, reference evidence, tests, and PR identity.
`aya/aya_factory/trace.py` reads native tool calls, results, and public messages from owned sessions and their children. It excludes reasoning, system prompts, and user prompts, redacts credential patterns, and caps each output. A background observer saves live records during native work.
Secrets and run records are excluded by `aya/.gitignore`.
`aya/aya_factory/mass_loop.py` stores frozen experiment inputs, upstream RHI receipts, development episodes, and one retained-workflow evaluation. `aya/aya_factory/telemetry.py` stores redacted development actions through Langfuse and verifies API readback. Evaluation-only traces contain aggregate metrics only. `aya/aya_factory/training.py` exports eligible, passing development answers into disjoint training and validation question sets.

## 4. How it works

`aya/aya_factory/intake.py:snapshot` freezes the issue, approved contract, and target commit.
`aya/aya_factory/pipeline.py:build` calls Crusoe, dispatches NemoHermes, and requires REA binary evidence.
`aya/aya_factory/evaluate.py:verify` compares candidate results with the pinned jq executable in isolated containers.
`aya/aya_factory/sql_pipeline.py:build` handles source/runtime migration from Fireworks into the Crusoe Developer Hub fork. `aya/aya_factory/sql_eval.py` checks SQLite behavior and `aya/aya_factory/sql_client.py` performs actual Crusoe tool calls. `aya/aya_factory/sql_runtime.py` executes only the accepted module digest against fresh GitHub data.
Passing candidates create a target pull request. CI must pass before local activation.
The repository-fixture MASS experiment uses the accepted SQL executor without changing its source. The public-SQL benchmark uses separate pinned SQLite databases and a restricted executor. The forked upstream RHI proposes and judges a new workflow through Crusoe. Native NemoHermes executes each candidate inside OpenShell. `aya/aya_factory/sql_benchmark.py` preserves the original three-variant fixture. The controller retains the prior workflow on a tied score. A separate, explicitly labeled supervised distillation smoke test uploads ten passing development answers and two validation answers to Crusoe. This stage does not claim an upstream MASS winning teacher when the bare reference was not beaten.
Stored trajectory selection uses actual Langfuse API readback and independent reports. It ranks comparable passing development answers by episode calls, tokens, and latency. Episode cost is not presented as measured per-question cost. Held-out data is excluded. A selected answer does not trigger a training job by itself.
`aya/aya_factory/trajectory_selection.py` binds each answer to a frozen evaluation and an API-verified trace revision. The training consumer rechecks these bindings. It submits only when ten training questions and two preassigned validation questions pass. Upload receipts bind to local file hashes. `aya/aya_factory/checkpoint.py` prepares a deployment recipe without creating a resource. Execution requires the exact recipe hash and an explicit duration; cleanup applies only to its owned deployment.

## 5. Contracts and invariants

- The proxy requires Onyx FULL_ADMIN_PANEL_ACCESS. Mutations require the same origin and a custom header.
- The browser never receives the host token, inference key, or GitHub credentials.
- Intake accepts only the configured owner's ready requests and a reviewed contract digest.
- GitHub failure cannot fall back to local fixtures.
- Each job owns a fresh directory. One job uses the dedicated feature worker at a time.
- Expected answers stay in the evaluator. The candidate receives input cases only.
- Activation binds to the source hash and the commit whose CI passed.
- MASS selection requires comparable development datasets, evaluator contracts, and executor hashes. Held-out questions cannot influence search or training.
- Training requires verified Langfuse provenance and exact input/output hashes. An unknown job-submission outcome cannot automatically create another job.
- Training success does not activate a model. A dedicated checkpoint deployment and independent tuned-model evaluation are still required.
- A public benchmark cannot run until its source, database files, and frozen selection pass preparation checks.
- Dataset identities remain separate. Scores from different benchmarks cannot decide a workflow replacement.

These checks live in the proxy, `aya/aya_factory/intake.py`, and `aya/aya_factory/pipeline.py`.

## 6. Relationships

Depends on [[auth-and-identity]] for administrator identity and [[chat-frontend]] for the application shell.
The separate Open WebUI adapter uses the verified component endpoint. It does not use Onyx chat storage.

## 7. Blast radius

Proxy changes affect authentication and browser requests. Check signed-in and signed-out access.
Evaluator changes affect both acceptance and runtime. Check against the pinned reference.
Sidebar and locale changes affect [[chat-frontend]]. Keep all locale keys in sync.

## 8. How to verify a change

Run the integration checks in `aya/tests/test_boundaries.py` with Python 3.12 and Docker.
Run the repository pre-commit hooks for changed files. Open the Factory view with an administrator session.
Start a real issue, inspect native evidence, inspect CI, then export an uploaded file in Open WebUI.

## 9. Footguns

The SQL contract supports one read-only query over a bounded repository dataset. It excludes Fireworks training and embeddings. The interface exposes raw receipts in collapsed details. A searchable action trace shows native calls and child activity. Starting a job scrolls to progress.
The first contract supports a bounded jq recipe subset. It does not implement arbitrary jq programs.
The OpenShell runtime reports Landlock unavailable on this Docker Desktop host.
Container and egress controls apply; a Landlock boundary is not verified.
The agent audit reports descendant calls. No aggregate token budget is enforced across descendants.
A failed SQL job can resume a native worker checkpoint before delivery. The controller rechecks GitHub identity and reruns acceptance; it preserves failure and resume events. Native status parsing only normalizes one extra closing brace after a complete JSON object, with an explicit journal entry.
The source-recovery examples use fixed model weights. MASS strategy search also keeps weights fixed. The optional Crusoe supervised job is a separate weight-training operation. A small smoke test does not establish generalization or recursive model improvement. There is no automatic tuned-model promotion before serving and evaluation succeed.
