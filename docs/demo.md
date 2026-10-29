# Reproducible offline demo

Install the locked dependencies from the [README](../README.md#quick-start), then
run from the repository root:

```sh
.venv/bin/python scripts/demo.py
```

The helper invokes the real CLI in subprocesses using the same interpreter. Mock
extraction and the stub reviewer make no model calls, regardless of whether API
credentials happen to be present. CrewAI's actual Flow/Agent/Task runs.

It checks the valid, ambiguous-date and incorrect-total fixtures and then runs
the complete mock evaluation. It stops if expected exit codes or review-boundary
checks differ. It is a checkpoint demonstration, not a replacement for the full
automated test suite.

Expected checkpoint output:

```text
valid: exit 0, validation valid, decision pending
ambiguous: exit 1, validation invalid, decision pending
incorrect_total: exit 1, validation invalid, decision pending
mock field recovery: 131/140 (93.57%)
quality: 16/17; known failure retained: unsupported_prose
integrity: 17/17; live model evaluation: not performed
Artifacts: local-data/portfolio-demo/ (JSON results refreshed; JSONL logs appended)
Demo matched the checkpoint. The standalone evaluation still exits 1 for the known quality failure.
```

The helper exits 0 only when those scenarios match the checkpoint. That does not
mean every invoice or evaluation quality check passed. The evaluation subprocess
must exit 1 and retain `unsupported_prose` as its only quality failure. Other
quality failures, an execution failure or an integrity failure stop the demo.

## Inspect the artifacts

Generated files are under ignored `local-data/portfolio-demo/`. Repeated demo
runs refresh the generated JSON results and append to the JSONL logs.

| File | What to show |
|---|---|
| `valid.json` | Source evidence, valid arithmetic, pending human decision |
| `ambiguous.json` | Null invoice date and its uncertainty reason |
| `incorrect_total.json` | Extracted `110.00` retained and `inconsistent_total` reported |
| `evaluation.json` | Per-field scores, unresolved metrics, known quality failure |
| `workflow-events.jsonl` | Three runs' stage metadata, counts and fixed codes |
| `evaluation-events.jsonl` | Evaluation runs distinguished by opaque run IDs |

For the complete software checks, run separately:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The complete suite now has 115 passing tests, including the pending-workbench
HTTP tests; the CLI demo's measured evaluation checkpoint is unchanged. The independent evaluation method
and its limitations are [documented here](../evaluation/README.md).

## Short recording outline

1. **Problem, 15 seconds:** explain that vendor text needs interpretation, while
   arithmetic and required fields need stable checks. State that all data is synthetic.
2. **Architecture, 30 seconds:** show the README diagram. Explain the reader,
   checker, bounded review task and pending decision boundary.
3. **Working cases, 45 seconds:** run the demo; inspect the valid record's evidence,
   the unresolved date and the incorrect total. A passing check is not approval.
4. **Evidence, 30 seconds:** show the 16/17 quality result and open the failed case.
   Explain why visible uncertainty can preserve integrity while extraction fails.
5. **Limits, 20 seconds:** state that no live-model evaluation occurred, the
   dataset is small and synthetic, and approval UI/exports remain future work.

Do not show credential settings or real business documents. The demo does not
publish a cloud snapshot, create an approval action or execute a payment.
