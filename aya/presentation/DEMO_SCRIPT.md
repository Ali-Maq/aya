# AYA: three-minute demo

AYA has two peer workflows: reverse engineering and agent improvement. Use the SQL example to demonstrate both. Read current API receipts rather than predicting an improvement.

## Three-minute main-deck story

- **0:00–0:25:** Software is cheaper to produce, but a feature still has to behave correctly and fit a real product. AYA starts with your repository, a reference and a behavior contract.
- **0:25–0:55:** Show the recovery workflow: inspect the reference, implement the component, test it independently and return a reviewable GitHub change.
- **0:55–1:20:** Explain the target outcome: a useful passing feature, the least expensive passing process, visible experiment cost and a controlled rollout. Label these as goals, not measured results.
- **1:20–1:55:** Explain the learning loop: compare workflows, retain verified examples, train a student and independently evaluate the next version. The current checkpoint still needs serving and evaluation.
- **1:55–2:25:** Explain the future customer loop: keep specs, tests, traces and decisions across models; use adoption and willingness-to-pay feedback to choose the next feature. No revenue impact has been measured.
- **2:25–3:00:** Open the live product or play the 94-second recorded experiment separately. Point to the evidence appendix for actual results, including no MASS accuracy gain and the three-of-six held-out result.

The detailed measured walkthrough below is for the evidence demo and Q&A. It must not be relabeled as an achieved ideal outcome.

## Before presenting

Open `/app/factory` on the Reverse engineering tab and `/app/factory?tab=improve` on the Agent improvement tab. Keep the [SQL feature PR](https://github.com/Ali-Maq/crusoe-developer-hub/pull/2), [MASS integration PR](https://github.com/Ali-Maq/mass/pull/1), and provider training job available.

The completed repository-fixture experiment is `76f46a90fc23427d`. The public Spider experiment `db5f5b51190a4b97` is separate: 12 development questions across six databases, then six held-out questions across three different databases. Check its actual status before showing it; never put the fixture's scores beside the public dataset as though they came from that dataset.

A fresh native build takes minutes. Show the completed run as recorded evidence, then make a new live product call. Do not substitute canned results for a failed live call.

## 0:00–0:20 — The product

“AYA recovers software capabilities and improves the agents that build them. These are two equal workflows. A feature request names your target repository and a reference; an improvement experiment names a task and its protected evaluator.”

Show the two primary tabs. The first example brings Fireworks SQL-tool behavior into the Crusoe Developer Hub fork.

## 0:20–0:50 — Reverse engineering

“Hermes investigated the reference through REA in the configured containers. The first component passed 117 of 118 independent checks. An empty SQL operation violated the contract; the gate required a repair. The accepted module passed 118 checks and a fresh-seed evaluation before GitHub delivery.”

Open the exact failure, repaired module, PR, and 54 passing target tests. This example uses source and runtime analysis. Do not call it binary decompilation or a reproduction of Fireworks reinforcement learning.

## 0:50–1:20 — Agent improvement

“A correct SQL executor does not guarantee a correct query. We held the executor and evaluator fixed, then used Sakana's actual MASS RHI code to propose and test a different agent workflow.”

Open the public Spider proposal and observable native trace. Read the recorded development scores: bare-model baseline 12/12 with one call and 4,544 tokens; initial Hermes v0 11/12 with eight calls and 48,451 tokens; MASS candidate v1 11/12 with 22 calls and 68,667 tokens.

“The proposal did not improve correctness. The two native workflows tied, so the workflow gate retained v0. The bare model was both more accurate and cheaper on the development split.”

The retained v0 passed **3/6 held-out questions**. State this explicitly. The bare baseline was not evaluated on held-out tasks, so do not call it better overall. Keep workflow selection separate from baseline eligibility for training-answer curation.

## 1:20–1:40 — Stored evidence

Show Best stored trajectories and its real Langfuse link.

The actual public selection chose all 12 answers from the bare baseline: ten training rows and two fixed validation rows, with zero held-out rows. The selector first requires independent correctness, then compares measured calls, tokens, and latency. Open the verified source trace and selection receipt.

The earlier repository-fixture selection chose all 12 one-call baseline answers after a 36/36 tie. That is a separate result. Neither selection establishes a winning MASS teacher.

Usage is measured for whole episodes. Do not invent per-answer costs. The current selection was consumed by public job `ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9`; read its current provider status separately from the earlier succeeded job.

## 1:40–2:05 — Actual training

“The public experiment’s verified baseline answers trained a Qwen3.5-9B student. Ten training rows and two fixed validation rows went to one Crusoe epoch. The provider reports success and 26,624 trained tokens.”

Open job `ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9`. Checkpoint: `ftmodel-2ac55e69-6a3c-4b2d-a3d1-0fd93bf5455a`.

“MASS alternates workflow search with training, then repeats with updated weights. This prototype completed one search round and verified final-answer distillation. The student still needs serving and independent evaluation before the next cycle.”

This is not the paper’s full tool-trajectory training recipe or a winning MASS teacher. No tuned-model quality, deployment, product activation, or recursive gain has been demonstrated.

## 2:05–2:30 — Public SQL benchmark

Show the live benchmark selector, [pinned public source](https://huggingface.co/datasets/xlangai/spider/tree/6232cc3fad6d54c62b3ba23a364083a98ff36a17/data), and the actual run result. This uses its own read-only database executor and one execution comparison per question, not three generated datasets.

The bare-model baseline completed 12/12 development questions with one call, 4,544 tokens, and 13.92 seconds. Both native workflows scored 11/12. A perfect baseline leaves no room for a development accuracy gain in this run.

The retained native workflow passed 3/6 held-out questions. This is a functioning measurement and training pipeline, not a successful accuracy-improvement result. Do not describe a small subset as a full Spider leaderboard result. Native comments claimed familiarity with Spider answers; possible memorization limits interpretation.

## 2:30–3:00 — Live product and review

Return to Reverse engineering and ask: “What is the total star count for each owner?” Show the generated SQL, actual rows, fresh source links, Crusoe receipt, and accepted executor commit.

“This product uses the delivered component. The evidence trail lets you inspect what was recovered, what failed, what changed, and what qualified for the next step.”

The live analyst is not evidence that the retained MASS workflow or fine-tuned model has been activated unless deployment is separately verified.

## Q&A: comparison with ordinary coding agents

A separate contract-only call to the same Crusoe model passed 107/118 component checks on both seeds. It used 2,268 tokens. The accepted AYA module used 98 planning/native calls and 191,554 cumulative tokens, excluding later product calls.

This was one task with unequal budgets and tools. It does not establish superiority over Claude Code or Codex, and it does not isolate REA's effect. Keep this component comparison separate from the 36-check natural-language benchmark.

The product's differentiator is an inspectable protocol: pinned reference behavior, independent acceptance, isolated execution, retained evidence, and explicit gates between workflow selection, training, serving, and promotion. The current experiment demonstrates that protocol; a larger matched-budget evaluation is still needed to quantify benefit.

## Q&A: execution boundary

Native episodes use fresh workspaces in one shared OpenShell worker. They do not have per-job filesystem isolation. The public v0 trace read an unrelated older fixture file in a sibling workspace; no current Spider gold SQL was observed. The generated SQL runs through separate restricted Docker executors. Native Landlock is unavailable on this host.

## If a dependency fails

Show the error, identify the failed dependency, and open the completed run's saved evidence. Label it as recorded. Do not retry a training submission casually or conceal a failed operation with a mock response.

Public SQL training job `ftjob-3f54c5ea7cee4dbcb1819004d2c1d7a9` succeeded with 26,624 trained tokens. Checkpoint `ftmodel-2ac55e69-6a3c-4b2d-a3d1-0fd93bf5455a` still requires serving and independent tuned-model evaluation.
