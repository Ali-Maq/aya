# AYA demo package

AYA has two peer workflows: reverse engineering and agent improvement.
The measured SQL example demonstrates both. The earlier four-track deck is archived in ignored local build storage.
The main presentation explains the target product and future customer-value loop in plain language. Actual experiment results remain in a separate evidence appendix. The narrated Remotion film is in ../video/.

The deck separates completed results from work in progress. `demo-manifest.json` records the exact PR and evidence links.
Update the manifest when a new run completes. Keep failures and scope limits in the record.

## What to show

1. Show the SQL feature contract and the rejected whitespace query.
2. Open Agent improvement, select the public Spider benchmark, and show its own protected development score (12 questions) separately from the earlier repository fixture.
3. Open the actual MASS proposal, retained workflow, six-question public held-out result, and verified Langfuse selection. Show only completed receipts; keep the earlier 36/36 fixture experiment separately labeled.
4. Ask a new live question and open the PR with CI evidence.

A fresh native build takes several minutes. Start it before the presentation, or identify the completed run clearly.
Do not present a saved result as a new build.

## Files

- `DEMO_SCRIPT.md`: stage script, Q&A, and failure handling.
- `TESTING_FEATURES.md`: contract tests, reproduction commands, and acceptance layers.
- `BENCHMARK.md`: primary public Spider semantics, earlier fixture semantics, and interpretation limits.
- `../PUBLIC_SQL.md` and `../specs/mass-public-sql.json`: pinned public source, 12/6 split, executor, and training gates.
- `RECORDING.md`: recorded-video notes and the longer stage-demo sequence.
- `demo-manifest.json`: evidence and completion state.
- `assets/`: screenshots from the actual local applications.
- `build-deck.mjs`: editable slide source. Uses the bundled Artifact Tool runtime.
- `AYA-MASS-demo.pptx`: final eleven-slide PowerPoint: six story slides and five evidence appendices.
- `preview/`: final slide previews, generated with the deck.

The screenshots show actual local results. They are evidence captures, not mockups.
The package does not include API keys, raw hidden model reasoning, or credentials.

## Rebuild

Run the builder with the bundled Node runtime after loading workspace dependencies.
Pass the runtime package path through `AYA_NODE_MODULES`.
Set `AYA_PRESENTATION_SKILL` to the installed presentation skill and `AYA_RUNTIME_PYTHON` to the bundled Python executable.
Use `AYA_PRESENTATION_ROOT` only when the package is in another directory.
Set `AYA_DECK_VERSION` to a new value for each finalized revision and `AYA_FINAL_PPTX` when creating a separate revision. The finalizer does not overwrite an existing deck.
The builder writes a private draft and a distinct final PowerPoint. It does not publish a website.

## Claims

AYA demonstrates reference inspection, restricted SQL execution, independent tests, repairs, and a PR bound to accepted source. Native Hermes episodes use fresh workspaces in one shared OpenShell worker; cross-run filesystem isolation is not enforced.
It does not yet establish superiority over Claude Code or Codex. Both can inspect software and write tests.
The recorded one-shot comparison uses unequal budgets. A matched-budget comparison remains future work.

The earlier repository-fixture MASS search tied at 36/36 and retained v0; its Qwen3.5-9B SFT smoke test succeeded. The public Spider baseline scored 12/12 development, both native workflows 11/12, and retained v0 scored 3/6 held-out. Baseline held-out performance was not evaluated. All 12 public training/validation answers came from the verified baseline; its new job must be labeled with the actual provider status. Neither run establishes a winning MASS teacher or tuned-model accuracy gain. Deployment and tuned-model evaluation remain separate gates.

Public SQL training job `ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9` succeeded with 26,624 trained tokens. Checkpoint `ftmodel-2ac55e69-6a3c-4b2d-a3d1-0fd93bf5455a` still requires serving and independent tuned-model evaluation.
