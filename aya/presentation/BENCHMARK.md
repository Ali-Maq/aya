# SQL benchmark identities and evidence

AYA exposes two distinct agent benchmarks. Keep their questions, executors, scores, and training receipts separate from the recovered component's 118-check contract suite.

## Current public benchmark: Spider subset

The current primary agent demo uses **12 development questions across six real SQLite databases and six held-out questions across three different databases**. Each question is evaluated against one database. It is not the earlier three-seed repository fixture.

The source is the [official XLang Spider archive](https://huggingface.co/datasets/xlangai/spider/tree/6232cc3fad6d54c62b3ba23a364083a98ff36a17/data), revision `6232cc3fad6d54c62b3ba23a364083a98ff36a17`, SHA-256 `5ddff97bb1d421282c593e8d30ce0ce107270f4dd4a21d60eba4bf287d5956b1`. The [Spider project](https://yale-lily.github.io/spider) identifies the dataset as CC BY-SA 4.0; cite Yu et al. (2018). Exact IDs, database hashes, selection rules, and pre-run exclusions are in [spider-benchmark.json](../specs/spider-benchmark.json).

Public inputs contain questions, CREATE TABLE schemas, and up to two sample rows per table. Submitted answers map question IDs to SQL. Expected SQL stays in the controller cache. The separate `public_db_executor.py` evaluates candidate and reference queries in the same pinned, networkless, non-root, read-only, resource-bounded container. It does not change the accepted repository analyst component.

A passing answer has the same column count and result rows. Aliases do not matter. Row bags preserve duplicates; row order matters only for reference SQL with top-level ORDER BY. This is single-database execution agreement on 18 questions, **not the official Spider test-suite metric or a leaderboard score**. Public questions may have appeared in model training. The actual native trace included comments claiming familiarity with Spider answers, so possible memorization is an observed concern. Coincidental query equivalence can pass one database. This subset has no explicit NULL-predicate questions; separate executor tests cover NULL and duplicates.

The fixed development inputs and evaluator hashes remain unchanged through MASS search. RHI receives development evidence only. Strict development improvement is required to select a candidate; ties retain v0. Only the selected workflow then receives the six held-out tasks. Held-out databases are disjoint, but public availability is not evidence that the model has never seen them.

Training uses independently passing development answers selected from verified Langfuse records. IDs `spider-dev-0667` and `spider-dev-0684` are fixed validation rows; ten other development IDs are the training rows. No held-out answers enter selection or training. The controller submits one Qwen3.5-9B supervised LoRA epoch only when all ten training rows and both validation rows pass. Otherwise it reports insufficient verified examples and submits nothing. Training success, deployment, tuned-model evaluation, and promotion are separate gates.

See [PUBLIC_SQL.md](../PUBLIC_SQL.md) and [mass-public-sql.json](../specs/mass-public-sql.json). The current adapter is pinned to MASS fork revision `2818e476eafd415d573c27d94b3335391a194605`; historical receipts preserve their own version. Model results belong in `demo-manifest.json`, not in the benchmark's self-check counts.

## Shared-worker limitation

Episodes use fresh workspaces in a shared OpenShell worker. Cross-run filesystem isolation is not enforced, and native Landlock is unavailable on this Docker Desktop host. The public v0 trace accessed an unrelated older fixture file in a sibling workspace; no current Spider reference SQL was observed. Separate SQL executor containers enforce their execution limits. This prototype does not establish per-job filesystem isolation or a formal security guarantee.

## Earlier repository-fixture benchmark

This document describes the completed synthetic repository fixture, not the newer public SQL benchmark. Keep all benchmark identities and scores separate.

The fixture has two evaluation layers:

| Evaluation | Subject | Cases |
| --- | --- | --- |
| Component contract | The recovered `query.execute` implementation | 118 checks per seed |
| NL workflow benchmark | The SQL or refusal produced for a question | 12 tasks across 3 datasets, or 36 checks per split |

The component comparison is complete. One contract-only Crusoe completion passed 107/118 on each seed.
The accepted component passed 118/118 on each seed. Their inference budgets differ substantially.

The NL benchmark supports the MASS workflow experiment. Its results depend on the actual runs.
Successful private-oracle validation confirms the evaluator works. It does not measure model performance.

## Frozen boundary

The benchmark lives in `aya_factory/sql_benchmark.py`. The runtime records its source hash before search.
It also records the accepted executor, contract, and dataset hashes. A mismatch must block comparison.

The model receives `public_tasks(split, seed)`. That view contains the schema, one dataset, and question IDs with text.
It excludes reference SQL and expected refusal labels. Refusal IDs do not reveal the expected action.

The controller retains `cases(split)` and its reference SQL. Only trusted reference queries run through the host oracle.
Model-generated queries execute through the accepted component in the restricted Docker evaluator.

## Splits and checks

Development and held-out splits each contain 12 distinct questions. Each split has ten SQL questions and two refusal questions.
The questions cover different tasks. They share ordinary SQL concepts, which a capable model may already know.

Each generated SQL statement runs on three deterministic datasets. The worker sees only the first snapshot.
The additional seeds change values and owner presence. They preserve the schema and behavior contract.
The datasets contain ties, zero, NULL, empty strings, Unicode, apostrophes, and literal wildcard characters.

The controller compares column count and ordered row values. Column aliases do not affect the score.
Question text specifies ordering where needed. A different column order or row order fails.
The evaluator does not use a model judge to determine SQL correctness.

Each question contributes three checks. Refusal questions repeat across the three datasets and therefore contribute six checks per split.
The report includes `task_passed` as well as total checks. A task passes only when all three dataset checks pass.

## Refusals

The answer format maps question IDs to `{"sql": "..."}` or `{"refused": true}`.
Refusal tasks ask for writes or external file/database access. The evaluator does not execute those requested operations on the host.
Missing answers, malformed answers, and incorrect refusals fail their checks.

## MASS selection

Development evidence can inform workflow proposals and selection. Held-out results must not enter the optimizer.
Freeze the retained workflow before evaluating its held-out performance. Preserve unsuccessful proposals and their costs.

Use the same executor and evaluation policy for initial and retained workflows.
If the initial workflow already passes all checks, report that ceiling. Do not manufacture a weaker starting point.

## Limitations

This is a small, synthetic repository-metadata benchmark. It is not Spider, BIRD, or a general SQL capability benchmark.
Three snapshots reduce literal-answer overfitting, but they cannot cover all databases or query plans.
Repeated refusal checks and shared question structure limit the statistical independence of the 36 checks.

One search run does not establish recursive self-improvement across tasks or model generations.
RHI changes a workflow at fixed weights. A weight-update claim requires a completed training job and an evaluated model artifact.

The module baseline uses one completion. The full recovery workflow uses many calls, tools, and repair feedback.
It does not isolate the benefit of any individual component, and it is not a Claude Code or Codex comparison.
