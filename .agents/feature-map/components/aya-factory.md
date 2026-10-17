# AYA Factory

**Verified against:** `7f12bab162` (2026-10-17)
**Domain:** aya-factory
**Edition:** CE extension.
**Owns:** `aya/`, `web/src/app/app/factory/`, `web/src/app/api/aya/`.
The verification includes the AYA working changes on this base.

## 1. What the user experiences

An administrator opens the Factory view in Onyx. It reads ready GitHub requests and displays real job records.
Each request names a target repository. Onyx is the factory interface.

## 2. Surfaces

The page uses the authenticated proxy in `web/src/app/api/aya/[...path]/route.ts`.
The host controller exposes requests, runs, and run details. A separate token protects the component endpoint.
The token names and local ports are defined in `aya/aya_factory/server.py:Handler`.

## 3. Data model

`aya/aya_factory/core.py:save` writes atomic JSON receipts. `Journal.emit` appends durable events.
Each run retains a frozen issue, contract, source hash, native agent audit, reference evidence, tests, and PR identity.
Secrets and run records are excluded by `aya/.gitignore`.

## 4. How it works

`aya/aya_factory/intake.py:snapshot` freezes the issue, approved contract, and target commit.
`aya/aya_factory/pipeline.py:build` calls Crusoe, dispatches NemoHermes, and requires REA binary evidence.
`aya/aya_factory/evaluate.py:verify` compares candidate results with the pinned jq executable in isolated containers.
Passing candidates create a target pull request. CI must pass before local activation.

## 5. Contracts and invariants

- The proxy requires Onyx FULL_ADMIN_PANEL_ACCESS. Mutations require the same origin and a custom header.
- The browser never receives the host token, inference key, or GitHub credentials.
- Intake accepts only the configured owner's ready requests and a reviewed contract digest.
- GitHub failure cannot fall back to local fixtures.
- Each job owns a fresh directory. One job uses the dedicated feature worker at a time.
- Expected answers stay in the evaluator. The candidate receives input cases only.
- Activation binds to the source hash and the commit whose CI passed.

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

The first contract supports a bounded jq recipe subset. It does not implement arbitrary jq programs.
The OpenShell runtime reports Landlock unavailable on this Docker Desktop host.
Container and egress controls apply; a Landlock boundary is not verified.
The agent audit reports descendant calls. No aggregate token budget is enforced across descendants.
The demo uses fixed model weights. Task repair is not model post-training.
