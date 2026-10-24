# Technical case study: evidence before more agents

## Problem and delivered scope

Vendor invoices contain facts that must be extracted, checked and reviewed before
a business records them. Document interpretation can be uncertain, while rules
such as arithmetic and required fields should be repeatable.

This project implements a CLI workflow over synthetic text: extraction, structured
handoffs, deterministic validation, bounded CrewAI review preparation, evaluation
and sanitized stage logging. It deliberately stops before approval, email sending
and financial actions. Implementation was AI-assisted; the evidence consists of
reproducible tests, fixtures and evaluation artifacts rather than a claim that
generated code is automatically correct.

## Decisions and trade-offs

**Separate interpretation from checking.** The extractor proposes source-backed
strings or unresolved fields. The validator handles dates, Decimal arithmetic,
required data and duplicates. This allows a wrong invoice total to be extracted
faithfully and then rejected by the arithmetic check.

**Preserve uncertainty.** Missing fields, ambiguous dates and conflicting sources
are distinct outcomes. Choosing a plausible answer would make the demo look more
complete while hiding the reason a person needs to review it.

**Constrain the agent's authority.** CrewAI coordinates ordered steps. Its one
review agent returns references to facts already produced by application code.
The renderer owns the summary, and agents cannot change the human decision. A
deterministic formatter would be simpler; this agent demonstrates a bounded
integration rather than a necessary source of new reasoning.

**Make provider access optional.** The OpenAI adapter is opt-in and checks structured
output locally. Mock extraction and stub review permit reproducible offline tests.
This trades natural-language coverage for predictable development behavior.

**Measure separate properties.** A correct extracted field, correct uncertainty
flag and preserved pending decision are different results. The evaluator scores
them separately instead of presenting one general-purpose "AI accuracy" score.

## Evidence

The checkpoint passed **98 automated tests**. Tests exercise real CrewAI scheduling
and task execution with fake model replies, plus mocked OpenAI responses. They
cover malformed input, numeric boundaries, component failure and the human-review
boundary. No paid calls or live-model accuracy tests occurred.

The independent synthetic annotations cover 17 cases and 153 field positions.
Of these, 140 fields have known values; mock extraction recovered 131 exactly
(93.57%). Thirteen fields are intrinsically unresolved. Unresolved detection
recorded 13 true positives, 9 false positives, 0 false negatives and 131 true
negatives. All 17 cases passed the specified pipeline integrity checks, while
only 16 passed every quality check.

**The useful failure is `unsupported_prose`.** All nine fields in a complete invoice
are knowable, but the mock parser cannot read its phrasing. It returns nulls and
flags them missing, reducing both extraction accuracy and unresolved precision.
The downstream validator and summary retain that problem. This demonstrates a
visible extraction limitation, not successful understanding of the document.

The report is generated from actual runs, includes a dataset fingerprint, and
reproduces byte-for-byte with the current implementation. Failed cases are not
removed from denominators. The evaluation exits nonzero while the known failure
remains. [Full methodology and results](../evaluation/README.md).

## What the numbers do not establish

This small developer-authored dataset is not held out or representative of real
invoices. Its grammar overlaps the mock parser, and field outcomes within a
document are correlated. For example, the unreadable fixture contributes nine
unresolved fields. A 100% unresolved recall here does not establish general recall.

Mock field recovery cannot establish live model accuracy, production reliability,
fraud detection or invoice authenticity. Source citations show where a candidate
appeared, not whether the model understood it correctly. Tests passing also do
not imply that a cloud snapshot was published or restored successfully.

## Explain it independently

- **Deterministic validation:** explicit rules need stable answers; a model
  is unnecessary for addition, date ordering and required-field checks.
- **Null values:** a null with evidence and a reason is more honest than
  a guessed date, vendor identifier or amount.
- **CrewAI's contribution:** explicit step coordination and a real, bounded agent
  lifecycle. A simpler fixed Python pipeline is a valid alternative.
- **The 93.57% result:** exactly 131 of 140 known ground-truth field values
  matched in this synthetic mock evaluation. It says nothing about a live model.
- **Quality and integrity:** extraction can miss data while
  still preserving uncertainty, exposing errors and keeping the decision pending.
- **Approval:** nobody approves in the current CLI. The human-review UI is future work.

## Next evidence to collect

Evaluate a configured live extractor on broader independently labelled synthetic
documents, recording provider/model identifiers, costs, failures and uncertainty.
Then add an explicit human-review interface and approved-only exports. Those steps
address current gaps more directly than introducing another agent.
