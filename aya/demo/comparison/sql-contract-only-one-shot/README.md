# One-shot SQL comparison

This experiment asks the same Crusoe model to implement the reviewed SQL contract in one completion.
The request provides no reference source, tools, independent test cases, or repair feedback.

The actual response used 659 input tokens and 1,609 output tokens. It completed in 9.301 seconds.
The source has not been edited. It passed AST admission, then 107 of 118 checks on each evaluation seed.
The accepted AYA module passed all 118 checks on those same seeds.

## Evidence

- `request.json`: exact request body, without credentials.
- `contract.json`: reviewed feature contract supplied to the model.
- `receipt.json`: provider response ID, model, usage, and hashes.
- `candidate.py.txt`: unchanged generated source, stored as evidence.
- `development/report.json` and `fresh-seed/report.json`: actual isolated evaluation results.
- `summary.json`: comparison results, measured budgets, and interpretation limits.

The model is `deepseek-ai/DeepSeek-V4-Pro` on Crusoe. The request limits output to 6,000 tokens.
The evaluator used the same case generator and seeds as the accepted AYA SQL module.
It executed the candidate only in the existing restricted Docker evaluator.

The baseline accepted a whitespace-only request. It also returned the wrong error code for limits and denied operations.
Those 11 failed checks remained unchanged across the two seeds. No repair call followed the evaluation.

## Interpretation limits

The AYA run has reference investigation, tool use, delegation, and repair feedback. Its budget is substantially larger.
Its recorded planning and native work used 98 model calls and 191,554 cumulative tokens.
That count excludes the four live verification questions and later product calls.

This is one task and one sample. It cannot isolate the effect of REA or any other individual workflow step.
No Claude Code or Codex baseline ran. Do not describe this as a comparison against those products.
Do not equate cumulative token counts with monetary cost. Cached tokens and provider pricing may differ.
