# MASS and the SQL workflow

AYA uses the actual [SakanaAI/MASS](https://github.com/SakanaAI/mass) RHI implementation.
The [Crusoe adapter](https://github.com/Ali-Maq/mass/pull/1) changes the model transport and adds task 1001.
It keeps the upstream workflow proposal and comparison logic.
The tested adapter revision is `9d2f8ac91fc115bcf78ecb5b08d750e68676cb52`.

The [live GitHub request](https://github.com/Ali-Maq/aya/issues/2) points to [the feature contract](specs/mass-sql.json).
Onyx hosts the factory interface. The accepted [SQL component](https://github.com/Ali-Maq/crusoe-developer-hub/pull/2) stays fixed.
MASS changes the workflow that turns questions into SQL. It does not rewrite the accepted executor during this experiment.

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

Each split has 12 questions. The evaluator checks each answer on three datasets: 36 checks per split.
Questions cover ordering, ties, grouping, NULL values, literals, and prohibited requests.
The worker sees the public fixture and questions. The optimizer receives development evidence only.
The controller owns expected answers, hidden variants, and final held-out evaluation.

The controller accepts an object keyed by question ID. Each value is exactly `{"sql":"..."}` or `{"refused":true}`.
Only the fixed SQL executor runs the generated SQL. Expected result rows stay outside the worker.

## Recorded result

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
The current training test uses ten passing development questions and two separate development validation questions.
It excludes all held-out questions. It uploads chat JSONL and submits one supervised LoRA epoch for `Qwen/Qwen3.5-9B`.
The native teacher is DeepSeek-V4-Pro; the student is Qwen. This is a final-answer distillation test.

This is **not a MASS winning-teacher training round**. Neither workflow beat the bare reference.
It does not reproduce the paper's trajectory ranking, full assistant-token training, or same-model weight cycle.
The small training set proves integration only. It cannot establish generalization or weight improvement.
The factory displays the provider's real job status, events, checkpoints, and errors.
The completed job is [`ftjob-d9d6409d3a2b4c67adebb74d0398064c`](https://console.crusoecloud.com/foundry/fine-tuning/jobs/ftjob-d9d6409d3a2b4c67adebb74d0398064c/overview).
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

Use the configured Onyx factory and select the MASS SQL experiment.
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
