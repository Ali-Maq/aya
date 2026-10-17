# Public SQL evaluation

AYA uses a fixed Spider subset with real SQLite databases. It has 12 development
questions across six databases and six held-out questions across three other databases.
No model has selected these questions. The controller fixes IDs before the first model call.

The source is the [official XLang Spider archive on Hugging Face](https://huggingface.co/datasets/xlangai/spider/tree/6232cc3fad6d54c62b3ba23a364083a98ff36a17/data).
The [Yale project page](https://yale-lily.github.io/spider) states the CC BY-SA 4.0 license.
The archive is 99,736,136 bytes. Its revision and SHA-256 are in
[spider-benchmark.json](specs/spider-benchmark.json). Cite Yu et al. (2018),
*Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic
Parsing and Text-to-SQL Task*. The upstream dataset keeps its CC BY-SA 4.0 license.
AYA does not relicense or commit the downloaded databases or reference SQL.

## What changes from the first experiment

The earlier repository fixture remains unchanged. The public benchmark uses joins,
aggregates, nested queries, set operations, and real stored data. It uses a separate
read-only database executor; it does not expand the accepted single-table component.

The split uses a fixed hash order of database names. Each selected database contributes
one JOIN question and one distinct query with multiple SELECT clauses. The manifest
records the exact selection rule, IDs, file hashes, and exclusions. Two annotation
errors and one ambiguous database were excluded before model execution. Reference SQL
is never corrected silently. This subset has no explicit NULL-predicate questions;
NULL comparison and duplicate-row behavior have separate executor tests.

Validation IDs `spider-dev-0667` and `spider-dev-0684` come from the last development
database. The other ten development IDs are eligible for training export. These two
validation IDs never enter gradient training. The six held-out IDs never enter
workflow search, training, or development trace selection.

A supervised job can start only with ten verified training answers and both fixed
validation answers. It uses one epoch of Qwen3.5-9B LoRA training, rank 16 and alpha 32.
Insufficient passing rows stop submission. Deployment and model promotion are not automatic.

## Boundaries and score

Workers receive question text, CREATE TABLE schemas, and at most two sample rows per
table. They submit `queries.json`, keyed by question ID, with exactly one `sql` field
per answer. The controller keeps reference SQL in a private cache. RHI sees only
public development inputs, submitted SQL, and measured development results.

Both candidate and reference SQL run in the same pinned Python container. The container
has no network, a read-only root, no capabilities, a non-root user, 256 MiB memory,
one CPU, and a 16 MiB temporary filesystem. Database mounts are read-only. SQLite
permits reads and approved functions only. It blocks writes, ATTACH, PRAGMA, and
extension loading. Each query has VM-step, time, SQL-size, column, and output limits.
No candidate SQL runs on the host. Schema inspection uses controller-owned queries
against checksum-verified public databases.

A question passes when column counts and result rows match. Column aliases may differ.
Unordered results use row bags that preserve duplicates. Order is checked only when
the source query specifies top-level ordering. Evaluation reports contain task IDs
and failure categories, not reference SQL or reference rows. Invalid answer envelopes
score zero. Changed database bytes fail before execution.

This measures **single-database execution agreement on an 18-question subset**.
It is not the official Spider test-suite metric or a leaderboard result. Public data
may have appeared in model training. A public held-out split is a controller boundary,
not a claim that models have never seen those questions. A tied score retains the
existing workflow; improvement requires a measured difference.

## Run

Use AYA's Python 3.12 environment and installed Docker runtime:

```bash
PYTHONPATH=aya python -m aya_factory.public_sql_benchmark prepare
PYTHONPATH=aya python -m aya_factory.public_sql_benchmark catalog
PYTHONPATH=aya python -m unittest discover -s aya/tests -p test_public_sql_benchmark.py
```

`prepare` checks the full archive checksum and extracts only manifest-approved files.
The cache is `aya/.state/public-sql`, or `AYA_PUBLIC_SQL_CACHE` when set. It writes a
preparation receipt. The UI marks the benchmark ready only when the receipt and all
selected file hashes match the manifest. Each evaluation verifies the file hashes again.

The live contract is [mass-public-sql.json](specs/mass-public-sql.json).
MASS adapter revision `1af6caf0cafa0a7761f4d3d286a27b1bc45a062a` includes public
context in the evidence bundle and the immutable runtime budget in its optimizer prompt.
It does not place development questions in the workflow that later runs held-out tasks.
Historical MASS receipts retain their original adapter revision.
