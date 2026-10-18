# Public Spider experiment db5f5b51190a4b97

Captured from real Crusoe and native NemoHermes calls. The factory source is
[`0fe69eac`](https://github.com/Ali-Maq/aya/commit/0fe69eac1290d39115ff51fc0655bc25093c22cd).
The request is [AYA issue 2](https://github.com/Ali-Maq/aya/issues/2).

| Episode | Execution agreement |
| --- | --- |
| baseline | 12/12 |
| v0 | 11/12 |
| v1 | 11/12 |
| heldout | 3/6 |

Native workflow selected: v0.
Experiment status: awaiting_deployment / Deployment required. Training status: succeeded.
Strict development accuracy improvement over the bare baseline: **No**.

The fixed public benchmark contains 12 development questions and 6 held-out questions
from disjoint real SQLite databases. These are single-database execution results,
not official Spider test-suite accuracy or a leaderboard score. Public questions
may have appeared in model training. Scores do not establish general agent superiority.

Native episode filesystem isolation failed. The v0 and v1 workers read previous
episode directories, including held-out output from the older fixture benchmark.
v1 also read this run's v0 output. The current Spider reference SQL stayed in the
host-owned evaluator. A full tool-call argument audit found no external-fetch marker
or current annotation path. This is not a complete runtime absence-of-access proof.
v1 code comments also claimed recall of known Spider reference patterns, so model
memorization is a possible explanation. The comments do not prove memorization or
its effect on scores. This public benchmark cannot establish generalization.
The direct baseline had no worker filesystem access. See `isolation-audit.json`.

The earlier attempt `bfe53d67173642b8` failed with HTTP 429 before producing an
answer. Its failure is preserved in `previous-attempt.json`; it has no model score.

This bundle includes aggregate episode scores, actual usage and response IDs, native
session counts, source hashes, GitHub identity, RHI receipts, workflow selection,
verified telemetry metadata, and available training status. Dollar costs remain unknown.
Training exports are final-answer distillation, not full tool-trajectory weight training.
A successful training job does not establish deployed-checkpoint quality.

Held-out questions, queries, outputs, and tool traces are excluded. Raw agent traces,
private reasoning, credentials, account identity, and local filesystem paths are excluded.
Public file hashes in `SHA256SUMS.json` refer to these sanitized copies. Original
execution hashes are retained in their receipts and may differ after redaction.
