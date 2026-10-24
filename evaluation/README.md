# Evaluation evidence — synthetic mock workflow

This report evaluates the deterministic mock extractor and real CrewAI workflow
with its stub reviewer. **It does not measure a live AI model's accuracy.**

## Reproduce

After installing the locked dependencies from the project README:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m operations_agent.evaluation --output evaluation/mock_report.json --log-json local-data/evaluation.jsonl
```

The full suite passed **98 tests** (79 prior tests plus 19 evaluation/observability
tests). The evaluation command currently exits **1**, intentionally: one known
mock-parser limitation fails the quality checks. The report is still written.
Exit 0 means all case quality and integrity checks passed; exit 1 means measured
failures; exit 2 means input/output or argument errors. No evaluation case is
skipped because it is labelled a known limitation.

`mock_report.json` is generated evidence, not hand-entered performance numbers.
It includes the SHA-256 of the exact dataset bytes and the CrewAI version. The
report excludes random record IDs, log timestamps and run IDs, so the same
dataset and implementation reproduce the same report. Logs append across runs.

## Dataset and methodology

`dataset.json` contains **17 manually annotated, synthetic cases**. Every case
specifies all nine expected fields, intrinsically unresolved fields, expected
extraction/validation outcomes, error/risk codes and whether extra attention is
required. Ground truth is not passed to the extractor or reviewer.

Cases cover supported labels and prose, missing invoice numbers and due dates,
ambiguous dates, conflicting email totals, incorrect arithmetic, impossible dates,
unknown vendors, duplicates, unreadable text, unsupported prose, excess decimal
precision, unsupported currency, zero amounts and embedded instructions.

Cases run in file order. Each `sequence` has a separate instance of the existing
validator; only the two cases in `duplicate_pair` share duplicate history. This
prevents unrelated examples with the same synthetic invoice number from becoming
accidental duplicates. Sequence order is part of the dataset contract.

Known-field accuracy compares exact extracted strings against non-null expected
values. Supported dates are compared after extraction's existing ISO normalization.
Amounts are not numerically coerced for scoring: source precision matters to the
validator. Null ground truth is excluded from this accuracy denominator, so
returning many nulls cannot inflate the score. Per-field counts are in the JSON.

Unresolved-field detection is scored independently over all 153 field positions:

- True positive: a genuinely missing/ambiguous/conflicting/unreadable field is flagged unresolved.
- False positive: a known field is unnecessarily flagged unresolved.
- False negative: a genuinely unresolved field is not flagged.
- True negative: a known field is not flagged unresolved.

Precision = TP/(TP+FP), recall = TP/(TP+FN), false-positive rate = FP/(FP+TN),
false-negative rate = FN/(FN+TP). An undefined denominator yields JSON null.
This measures binary unresolved detection, not accuracy of the unresolved reason.

Pipeline outcome matching compares extraction status, validation status, error
codes, risk indicators and extra-attention routing to the annotations. It measures
the combined pipeline, not validator accuracy independently of extraction.
All records require a human decision; "extra attention" means errors or flags,
not whether human review is necessary.

Separate integrity checks verify that unresolved facts are not filled, each stage
is visited, errors and uncertainty appear in the summary, extraction mismatches
trigger attention, and the record remains pending. Runner exceptions and malformed
outputs remain failures in the denominators instead of disappearing from results.

## Measured mock results

| Measurement | Result |
|---|---:|
| Runner execution failures | 0 / 17 |
| Known fields extracted correctly | 131 / 140 — 93.57% |
| Unresolved detection: TP / FP / FN / TN | 13 / 9 / 0 / 131 |
| Unresolved precision | 59.09% |
| Unresolved recall | 100% |
| Unresolved false-positive rate | 6.43% |
| Unresolved false-negative rate | 0% |
| Expected pipeline outcomes matched | 16 / 17 |
| Cases passing every quality check | 16 / 17 |
| Cases passing every integrity check | 17 / 17 |

The failing case is `unsupported_prose`: a complete invoice written outside the
mock reader's documented grammar. All nine known fields remain null and are
flagged missing, producing nine false positives. Validation reports missing
fields and the review summary retains those errors. This is a quality limitation
with preserved review routing, not a successful extraction.

## Structured logging

For a single invoice:

```sh
.venv/bin/python -m operations_agent samples/invoice.txt --format text --orchestrate --known-vendor 'Demo Supplies' --log-json local-data/run.jsonl
```

Each run emits pipeline and extraction/validation/review start/finish events with
an opaque run ID, UTC timestamp, fixed statuses, counts, allowlisted error codes
and review flags. Events never contain invoice values, vendor names, invoice
numbers, source filenames, source text, summary text, keys or raw exceptions.
Unrecognized error strings become `unrecognized_code`. Framework logging is
temporarily suppressed inside the serial runner to prevent arbitrary exception
text from escaping; its previous logging state is restored afterward.

An event-sink failure adds `observability_failed` to the returned record, review
summary and review flags. Processing continues, but the failure is not hidden.
If a sink fails, its log may be incomplete; the returned record is authoritative
for that failure. JSONL is append-only per invocation, without rotation, retention
management or concurrent-writer guarantees. Keep generated logs in ignored
`local-data/`; the measured synthetic report is the intended shareable artifact.

## Limits and demonstration

This is a small developer-authored regression dataset, not a held-out or
representative benchmark. Supported examples overlap the parser's documented
grammar. Several unresolved labels belong to one unreadable document; field
results are correlated. No confidence interval, general fraud claim, production
reliability claim or real-model accuracy claim follows from these numbers.

The evaluator is deliberately mock-only to avoid accidental provider charges.
Before reporting live AI quality, run a separately identified live evaluation
with a configured provider/model, record failures and costs, and use a broader
independently labelled dataset. No live model call occurred in this milestone.

A short portfolio demonstration can show: a valid invoice's evidence and pending
decision; the ambiguous-date and incorrect-total fixtures requiring attention;
the failing unsupported-prose evaluation case; the JSONL stage events; and the
98-test result. Human approval UI and approved exports remain future work, so the
application should be presented as a tested processing workflow, not a finished
financial operations product.
