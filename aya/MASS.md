# MASS and the SQL workflow

AYA uses the actual [SakanaAI/MASS](https://github.com/SakanaAI/mass) RHI implementation.
The [Crusoe adapter](https://github.com/Ali-Maq/mass/pull/1) changes the model transport and adds task 1001.
It keeps the upstream workflow proposal and comparison logic.
The public benchmark pins adapter revision `2818e476eafd415d573c27d94b3335391a194605`.
The earlier fixture experiment used `9d2f8ac91fc115bcf78ecb5b08d750e68676cb52`.

The [live GitHub request](https://github.com/Ali-Maq/aya/issues/2) covers the [public benchmark contract](specs/mass-public-sql.json) and [earlier fixture contract](specs/mass-sql.json).
Onyx hosts the factory interface. The accepted [SQL component](https://github.com/Ali-Maq/crusoe-developer-hub/pull/2) stays fixed.
MASS changes the workflow that turns questions into SQL. It does not rewrite the accepted component.
The public benchmark uses a separate restricted SQLite evaluator for its real databases.

## Measured loop

1. Freeze the task, public development data, contract, and evaluator hash.
2. Run a bare Crusoe baseline and the initial native Hermes workflow.
3. Score each answer against a trusted SQLite result oracle.
4. Give the measured development output to the actual MASS optimizer.
5. Execute the proposed workflow with native Hermes in OpenShell.
6. Run the upstream model-judge comparison and the independent score gate.
7. Retain a new workflow only when its development score strictly improves.
8. Evaluate the selected workflow on held-out questions.
9. Verify redacted Langfuse records through API readback.
10. Prepare a separate supervised training test from verified development answers.

The current public benchmark freezes 12 development questions and six held-out questions from separate Spider databases.
It uses joins, grouping, and nested queries from the pinned Hugging Face archive.
Each answer is checked on its original SQLite database. This is not the official Spider test-suite metric.
The worker receives public questions, schemas, and limited sample rows. Reference SQL stays in the host evaluator.
See [PUBLIC_SQL.md](PUBLIC_SQL.md) for provenance, licensing, selection, and reproducible preparation.

### Earlier fixture contract

Each earlier fixture split has 12 questions. The evaluator checks each answer on three datasets: 36 checks per split.
Questions cover ordering, ties, grouping, NULL values, literals, and prohibited requests.
The worker sees the public fixture and questions. The optimizer receives development evidence only.
The controller owns expected answers, hidden variants, and final held-out evaluation.

The controller accepts an object keyed by question ID. Each value is exactly `{"sql":"..."}` or `{"refused":true}`.
Only the fixed SQL executor runs the generated SQL. Expected result rows stay outside the worker.

## Public Spider result

Run [`db5f5b51190a4b97`](demo/evidence/mass-public-sql/db5f5b51190a4b97) used DeepSeek-V4-Pro on Crusoe.
Its factory source was `0fe69eac1290d39115ff51fc0655bc25093c22cd`.
The earlier attempt `bfe53d67173642b8` failed with HTTP 429 before an answer. It has no score.

| Stage | Execution agreement | API calls | Tokens | Seconds | Child sessions |
| --- | --- | --- | --- | --- | --- |
| Bare development baseline | 12/12 | 1 | 4,544 | 13.92 | 0 |
| Native initial workflow v0 | 11/12 | 8 | 48,451 | 182.71 | 1 |
| Native MASS candidate v1 | 11/12 | 22 | 68,667 | 315.38 | 1 |
| Selected v0 on held-out databases | 3/6 | 9 | 35,003 | 101.34 | 0 |

Three actual upstream RHI calls used another 40,840 tokens. Both judges preferred the bare baseline over native workflows.
MASS recorded `beats_reference=false`. The controller retained v0 among native candidates because v1 tied its score.
The bare baseline was better on development. It was not run on this held-out split.
These results show no workflow accuracy improvement and do not establish generalization.

The native workers accessed other episode directories, including older fixture held-out answers.
v1 also read this run's v0 output. This run does **not** demonstrate episode filesystem isolation.
A read-only audit inspected complete arguments for 29 tool calls across all four development sessions.
It found no external-fetch marker or current Spider reference-file path. This is not a complete runtime security proof.
Some code comments claimed familiarity with benchmark answers. That suggests possible memorization, without proving its effect on scores.
The public evidence contains IDs, hashes, and aggregate findings. It excludes raw comments and held-out contents.

The separate corpus selector verified Langfuse records and chose all 12 direct-baseline answers.
Those answers passed with fewer calls and tokens. Their direct request had no native-worker filesystem access.
The export contains ten training rows, two preassigned validation rows, and zero held-out rows.
The bounded Qwen3.5-9B supervised job is
[`ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9`](https://console.crusoecloud.com/foundry/fine-tuning/jobs/ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9/overview).
Its latest published status is in the [provider receipt](demo/evidence/mass-public-sql/db5f5b51190a4b97/training/receipt.json).
Crusoe reported success and 26,624 trained tokens. It registered checkpoint `ftmodel-2ac55e69-6a3c-4b2d-a3d1-0fd93bf5455a`.
This confirms training completion. Deployment and independent checkpoint evaluation remain required.
This remains final-answer distillation, not a MASS winning-teacher training round.

## Earlier fixture result

Run `76f46a90fc23427d` used `deepseek-ai/DeepSeek-V4-Pro` on Crusoe.

| Stage | Recorded evidence |
| --- | --- |
| Bare baseline | 36/36 development checks |
| Initial workflow v0 | 36/36; eight native model calls; zero child sessions |
| Actual RHI proposal | Response `37998c5e287748c4b0a56a3d08434f76`; 3,592 input and 1,510 output tokens |
| Revised workflow v1 | 36/36; 14 native model calls; zero child sessions |
| RHI comparisons | Both ties; `beats_reference=false` |
| Independent selection | Retained v0; ties cannot replace it |
| Held-out evaluation | Selected v0 passed 36/36 |
| Separate supervised test | Crusoe reported success; 10,568 trained tokens |

The three RHI calls used 14,673 tokens in total. Cost is unknown in the receipt, not zero.
The proposal asked for parallel specialists despite the preserved execution boundary.
The controller retained its runtime limits. The native audit recorded no child sessions in either development episode.
This shows why a proposed workflow needs execution and independent acceptance.

The benchmark was too easy for this model to establish an accuracy gain.
No comparison here proves that AYA is better than another coding agent.
The run demonstrates actual workflow search and a correct decision to reject an unproven change.

## Langfuse and training

`telemetry.py` stores redacted inputs, outputs, tool activity, model usage, scores, and version hashes.
It verifies the stored trace through the Langfuse API before it exports training data.
Held-out runs expose aggregate scores only. Private reasoning and credentials are excluded.

`training.py` checks that the Langfuse revision matches the evaluated answers, dataset, task, and selected workflow.
Each bounded training test uses ten passing development questions and two separate development validation questions.
It excludes all held-out questions. It uploads chat JSONL and submits one supervised LoRA epoch for `Qwen/Qwen3.5-9B`.
The native teacher is DeepSeek-V4-Pro; the student is Qwen. This is a final-answer distillation test.

The earlier fixture test was **not a MASS winning-teacher training round**. Neither workflow beat the bare reference.
It does not reproduce the paper's trajectory ranking, full assistant-token training, or same-model weight cycle.
The small training set proves integration only. It cannot establish generalization or weight improvement.
The factory displays the provider's real job status, events, checkpoints, and errors.
The earlier fixture job is [`ftjob-d9d6409d3a2b4c67adebb74d0398064c`](https://console.crusoecloud.com/foundry/fine-tuning/jobs/ftjob-d9d6409d3a2b4c67adebb74d0398064c/overview).
It registered checkpoint `ftmodel-cee03aea-b639-4bd6-bd18-40412f3713ac`.
This confirms an actual training job. It does not establish trained-model accuracy or improvement.

## Deployment is a separate gate

A successful training job registers a checkpoint. It does not make that checkpoint available in the serverless pool.
Crusoe requires a self-serve deployment for a custom LoRA model.
See the [official deployment guide](https://docs.crusoecloud.com/self-serve-deployments/quickstart/index.html).

A live project lookup found a compatible Qwen3.5-9B throughput flavor: one H100 at $5.50 per hour.
Quota was not available through the Intelligence key's generic cloud quota endpoint.
No deployment or trained-model improvement is implied by that lookup.

The next cycle must call the actual deployed checkpoint alias and pass a new independent evaluation.
Calling the original base model again does not close the weight-update loop.
Do not promote the checkpoint based only on training loss, job completion, or its model-judge score.

## Reproduce and inspect

Use Agent improvement in the configured Onyx factory. Select the public Spider benchmark or the labeled earlier fixture.
The authenticated frontend proxies requests to `/mass`; the controller creates a fresh run identity.
Each real run makes provider calls. It can submit the bounded supervised training test described above.

Set `AYA_MASS_ROOT` to the adapter checkout. Use Python 3.12 with AYA's [requirements](requirements.txt).
The actual hosted RHI calls used OpenAI client 2.24.0 and HTTPX 0.28.1.
This adapter subset does not need the full upstream local-vLLM or weight-training dependency stack.
Do not combine AYA's pins with the full upstream requirements in one install command.
The current setup uses the installed NemoClaw worker and a hosted model endpoint.

Local evidence is under `.state/mass/<run-id>/`:

| Path | Content |
| --- | --- |
| `manifest.json`, `contract.json`, `dataset.json` | Frozen task context |
| `<run-id>-baseline/`, `-v0/`, `-v1/` | Actual queries, independent results, and native audit |
| `rhi/` | Upstream prompts, model receipts, workflow versions, and comparison records |
| `selection.json` | Independent decision and upstream verdict |
| `<run-id>-heldout/` | Final evaluation; excluded from optimizer and training export |
| `training/` | Dataset manifest, uploads, job request, provider events, and checkpoint status |

[Published MASS evidence](https://github.com/Ali-Maq/mass/pull/1) removes host paths and secrets.
The [original SQL delivery](https://github.com/Ali-Maq/crusoe-developer-hub/pull/2) records the component tests and CI.
A stored response is labeled as evidence. It is never used as a substitute for a new live call.
