# Implementation reference

This page preserves the original CLI milestones and their historical test
checkpoints. The later [pending-review workbench](workbench.md) reuses that
pipeline; see the repository README for the latest complete test count.

An incremental application for **synthetic data only**. Mock or opt-in OpenAI
extraction feeds an unchanged deterministic validator. Milestone 3 adds an
optional CrewAI Flow and bounded review agent. The original baseline commands
still work without third-party packages; orchestration requires the installation
below.

Milestone 4 adds a 17-case labelled synthetic dataset, an offline evaluation
runner and opt-in structured logs. [Evaluation methodology and measured evidence](../evaluation/README.md)
separate extraction quality from workflow integrity and live-model accuracy.

## Install CrewAI orchestration

Tested on Linux with Python 3.12. CrewAI 1.15.30 supports Python >=3.10,<3.14;
this project requires Python >=3.12,<3.14. From the repository root, using `uv`:

```sh
uv venv .venv
uv pip sync --python .venv/bin/python --require-hashes requirements.lock
uv pip check --python .venv/bin/python
.venv/bin/python -m unittest discover -s tests -v
```

`requirements.in` declares CrewAI 1.15.30. `requirements.lock` pins its resolved
dependencies and artifact hashes, generated for Linux/Python 3.12. No optional
tools/provider extras are requested. CrewAI itself pulls a substantial dependency
graph, including database libraries; the application does not instantiate a
database. A test blocks SQLite connections during import and processing.
Initial package installation needs package-registry access. Subsequent mock
workflow runs and tests need no network or API credentials.

## Run

Python 3.12 or newer is required. From the repository root:

```sh
python3 -m operations_agent samples/invoices.json --known-vendor 'Demo Supplies'
python3 -m operations_agent samples/invoice.txt --format text --known-vendor 'Demo Supplies'
python3 -m operations_agent samples/invoice.txt --format text --email samples/conflicting_email.txt --known-vendor 'Demo Supplies'
python3 -m operations_agent tests/fixtures/milestone2/valid.txt --format text --mode mock --known-vendor 'Demo Supplies'
python3 -m operations_agent tests/fixtures/milestone2/ambiguous.txt --format text --mode mock --known-vendor 'Demo Supplies'
python3 -m unittest discover -s tests -v
```

Run the full CrewAI workflow with the virtual environment's interpreter:

```sh
.venv/bin/python -m operations_agent samples/invoice.txt --format text --mode mock --orchestrate --known-vendor 'Demo Supplies'
.venv/bin/python -m operations_agent tests/fixtures/milestone2/ambiguous.txt --format text --orchestrate
.venv/bin/python -m operations_agent samples/invoice.txt --format text --orchestrate --log-json local-data/run.jsonl
```

Output remains a JSON array, now including `review_summary` and `workflow` details.
`--orchestrate` requires text input. Its exit codes are 0 for completed extraction,
validation and review preparation; 1 for validation/extraction issues or a handled
workflow failure; and 2 for invalid input/arguments. Zero still means pending
human review. Baseline runs without `--orchestrate` retain their earlier behavior.

Input is a JSON array of invoice objects. Use decimal strings for money and
YYYY-MM-DD dates; missing values remain null. The sample includes a valid invoice,
a missing invoice number with an incorrect total, and a duplicate.
CLI exit codes: 0 means extraction (if used) and validation passed, 1 means
validation or extraction review issues were found, and 2 means input could not be
read. Results are JSON; input stays unchanged. A zero exit code never means approval.

JSON objects with repeated field names are rejected, even if their values match,
so the parser never silently discards information. Bare `NaN` and `Infinity` tokens
are rejected as malformed JSON. Excessively nested JSON gets a controlled input
error. An empty array is an accepted empty batch, not evidence of invoice processing.

## Extraction and uncertainty

`--format text --mode mock` is the default offline reader. It never reads API
credentials or makes model requests. It accepts `Label: value` lines from
`samples/invoice.txt` and narrow sentence patterns like this synthetic example:

> Invoice SYN-101 from Demo Supplies. It was issued on October 1, 2026; due on
> October 31, 2026. The currency is USD. Subtotal is 100.00; tax is 5.00;
> total is 105.00. This invoice is covering synthetic office supplies.

The exact sample is in `tests/fixtures/milestone2/valid.txt`. The mock is a small
rule-based parser, not a general language model. Unsupported prose stays missing.
Optional `--email` supplies additional UTF-8 source text; no inbox is connected.

Each extracted value includes source and line evidence. Missing fields remain
null. Conflicting values within a document or between document and email remain
unresolved with both values retained. `missing_fields`, `uncertain_fields`, and
`conflicts` are separate categories. Dates written as `YYYY-MM-DD` or English
month-first dates such as `October 1, 2026` are supported. Numeric slash dates such
as `03/04/2026` are marked uncertain, not guessed. Unsupported date formats also
require review. Impossible ISO calendar dates still reach the validator.
Amounts and dates then pass through deterministic validation.
Repeated exactly matching values agree; semantically similar but different values
are conservatively treated as conflicting. Unrecognized lines are ignored.
No confidence score is invented. Text without supported invoice fields is flagged
for review. Extraction statuses are `extracted`, `needs_review`, and (AI errors)
`failed`. Even failed AI extraction produces a pending record with validation
errors and `extraction_needs_review`, rather than silently falling back to mock.

## Optional AI mode

AI mode sends the supplied synthetic text to OpenAI's Responses API using HTTPS
and strict JSON Schema output. It supports arbitrary prose to the extent the
selected model can interpret it; model accuracy is not guaranteed or measured by
the offline tests. It is opt-in, requires provider access and may cost money.

Set credentials securely in the process environment using `INVOICE_AI_API_KEY`
(preferred in cloud settings) or `OPENAI_API_KEY` (fallback). Never put a real key
in source files, commands saved to shell history, or chat. `.env` files are ignored
by Git but are **not automatically loaded**. Also set `INVOICE_AI_MODEL` to a model
available to your account that supports Responses API strict JSON Schema output.
There is deliberately no assumed free/default model. Check your provider's model
availability, pricing, and usage limits before running this command:

```sh
# After securely configuring the key and INVOICE_AI_MODEL:
python3 -m operations_agent tests/fixtures/milestone2/valid.txt --format text --mode ai --known-vendor 'Demo Supplies'
```

Cloud environments also need HTTPS access to `api.openai.com`; enable that
destination in environment settings when using AI mode. Missing credentials or
model configuration produce a reviewable failure without making a request.
Do not paste secrets into chat. No credential or network setting is needed for
mock mode or the test suite.

The request provides no tools and separates application instructions from source
data. Generated output must satisfy an exact locally checked schema. Each non-null
field must equal an evidence token present on the cited source line. Contradictory
evidence clears that field; unsupported values become uncertain. Dates are
normalized by application code, not guessed by the model. No arithmetic is repaired.
Malformed JSON, unexpected fields/types, fabricated source citations, refusals,
incomplete replies, and connection failures result in reviewable failure.

The adapter uses a fixed HTTPS endpoint, normal TLS verification, a 30-second
network timeout, a 256 KiB response cap, blocked redirects, `store: false`, and no
automatic retries. `store: false` does not mean the provider has no retention;
consult its data policies. Error messages omit provider bodies and credentials.

API contracts were checked against current official sources before implementation:

- [OpenAI client documentation](https://github.com/openai/openai-python#usage)
- [Responses request parameters](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_create_params.py)
- [Structured-output format](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_format_text_json_schema_config_param.py)
- [Responses message format](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_output_message.py)

The documentation website was blocked by this environment's network policy;
the official repository documentation and API definitions were accessible.

PDFs, scanned images, OCR, multiline fields, and attachments are not supported.
Do not pass binary documents as text. Combined input has a one-million-character
limit checked after reading. Text contents never execute code or change approval
state. Evidence checks cannot establish that the model chose the correct field
meaning, found every conflict, or resisted every prompt injection. Human review
remains necessary. Input is read into memory before the text size check.

## Architecture

Structured JSON or text → mock/AI extraction (text only) → typed invoice →
deterministic validation → pending human review.

The extractor is the reader: it proposes values and records their source. The
validator is the checker: it independently checks dates, arithmetic, required
information, and duplicates. Neither is an approver. A successful extraction or
validation never changes `human_decision: "pending"` or
`processing_status: "awaiting_review"`. A review UI is a future milestone.

With `--orchestrate`, the actual CrewAI Flow runs:

```text
@start: existing mock/AI extractor
  → @listen: existing deterministic Validator
  → @listen: bounded review Agent + Task
  → application-rendered summary and pending review record
```

The Flow stores extraction evidence, validation results, visited steps, and workflow
issues in structured state. Logical validation errors are review findings, not
exceptions that terminate processing. Component exceptions are recorded as stage
failures. If validation fails to execute, its status is `unavailable`, never
`valid`. `completed_steps` means the step finished handling its outcome, including
handled failures; inspect the issue lists for success/failure details.

There is **one review agent**, not separate LLM extraction/validation agents.
Extraction reuses the established interface. Validation is ordinary Python, which
is simpler and more reliable for arithmetic and explicit business rules.

The review agent's task returns only a JSON list of references to precomputed
findings. It cannot supply invoice values or prose. The application requires
every reference exactly once and renders canonical, quoted facts, evidence,
uncertainty and errors in a stable order. Invalid output or a task/model failure
uses a deterministic summary with a visible `review_agent_task_failed` issue;
extraction and validation are not rerun. The agent has no tools, delegation,
code execution, payment actions, or decision-changing interface.

A deterministic formatting function would be simpler for this responsibility.
The single agent demonstrates a constrained, testable CrewAI handoff; it does
not contribute independent financial reasoning. Its default `ReviewPlanStub`
implements CrewAI's `BaseLLM` interface and returns the provided references. It
is a fake model, not simulated accuracy. Both `--mode mock` and `--mode ai` use
this stub reviewer; `--mode ai` opts into the existing OpenAI extractor only.
Library callers can inject a `BaseLLM` for testing the review boundary. No live
review-model configuration is provided by the CLI.

The review Task executes directly under the Flow using `Task.execute_sync`.
We deliberately do not instantiate `Crew`, which initializes SQLite replay
storage in this pinned release. Memory and persistence are not used. Telemetry
and tracing are disabled before import. A narrow, version-checked runtime adapter
redirects CrewAI 1.15.30's import-time credential-directory initialization into
ignored `local-data/crewai`; that release ignores its storage setting for this
one path. This uses one inspected private method and must be revisited on upgrade.
It does not copy existing home credentials, require CrewAI login, or configure
provider secrets. Any generated encryption key is local framework metadata.

The synchronous wrapper captures framework stdout and drains pending events to
keep CLI JSON clean. It changes process-wide framework settings and redirects
stdout temporarily: it is intended for serial CLI use, not concurrent server
requests or notebooks with an already-running event loop. Framework logging is
temporarily suppressed and restored to avoid leaking arbitrary exception text.
Application stage logs use counts, statuses and allowlisted codes only. Logs are
opt-in via `--log-json`; a write failure remains visible as `observability_failed`.

- `operations_agent/validation.py`: data models and deterministic rules.
- `operations_agent/extraction.py`: mock parsing, dates, evidence, uncertainty.
- `operations_agent/ai_extraction.py`: OpenAI HTTP adapter, schema, response checks.
- `operations_agent/json_input.py`: strict JSON decoding shared by input and AI output.
- `operations_agent/orchestration.py`: Flow, bounded review task, summary and failure handling.
- `operations_agent/crewai_runtime.py`: pinned-release runtime compatibility adapter.
- `operations_agent/observability.py`: sanitized JSONL stage events.
- `operations_agent/evaluation.py`: offline dataset runner and independent scoring.
- `evaluation/`: synthetic ground truth, generated report and methodology.
- `requirements.in` / `requirements.lock`: dependency declaration and hashed installation lock.
- `operations_agent/__main__.py`: command-line input and JSON output.
- `samples/`: synthetic invoice examples.
- `tests/`: validation and CLI regression tests.

Decimal arithmetic avoids binary floating-point rounding errors. Rules check
required fields, calendar dates, date ordering, supported currencies, nonnegative
amounts, subtotal plus tax, and duplicates. Unknown vendors are review indicators.
Configure known vendors with repeated `--known-vendor` arguments.

## Baseline audit

The full suite passed **36 tests** after the baseline audit (21 existing tests plus
15 new test methods, with parameterized subcases). Run the command above to verify
the current checkout; this count is not an AI accuracy measurement.

Audit coverage includes every required field being omitted, null, empty,
whitespace-only, or given unexpected JSON types; monetary limits and precision;
leap days and date formats; duplicate identity and lifetime; malformed JSON and
ambiguous repeated keys; and caller-supplied approval fields being ignored.

Fixes isolate arithmetic from caller decimal settings, reject duplicate JSON keys
and nonstandard numeric constants, and handle excessive nesting without a traceback.
Arithmetic uses its own temporary decimal settings, like a calculator with a
known precision, without changing the caller's settings.

Existing policies are preserved: omitted/null/empty fields are missing;
whitespace-only fields are invalid. Values with more than two stored decimal
places (including `1.000`) are invalid rather than silently rounded. Integer money
values are supported, floating-point values are rejected. Decimal string syntax
accepted by Python, including exponent notation and underscores, remains supported
when its value and stored precision meet the monetary rules. Unknown extra input
fields are ignored and cannot set the human decision or processing status.

## Milestone 2 validation

The complete suite passed **58 tests**: the previous 36 plus 22 new test methods,
with additional subcases. Every test runs offline without real credentials or
paid requests. AI tests inject synthetic Responses API replies, test the HTTP
adapter with simulated transport, and exercise both modes through the CLI and
validator. Fixtures cover valid invoices, missing fields, ambiguous dates,
incorrect totals, unreadable text, malformed replies, and provider failures.

These results verify integration and error handling, not real model quality.
No live provider call was made because no API key/model was configured. The
validator source was preserved unchanged for this milestone.

## Milestone 3 validation and official references

The complete suite passed **79 tests** (58 previous tests plus 21 orchestration
tests). The tests use the installed CrewAI Flow, Agent and Task implementations;
the framework is not replaced by a fake orchestrator. Stub/scripted models and
synthetic OpenAI responses cover success, logical validation failures, missing and
uncertain extraction, conflicting evidence, malformed handoffs, task/model errors,
and the pending decision boundary. A clean subprocess blocks network, DNS and
SQLite calls during import and a complete mock run. Dependency compatibility also
passes `uv pip check`.

No live model test was run. These results verify orchestration and boundary
handling, not real-model accuracy. Both extraction modules and the validator
were preserved unchanged, checked by matching their pre/post file hashes.

CrewAI's documentation site was blocked by network policy. Before implementing,
the current official repository documentation, public API definitions and installed
1.15.30 source were inspected:

- [Official Flow/Crew guide and example](https://github.com/crewAIInc/crewAI#using-crews-and-flows-together)
- [Official model base interface](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/src/crewai/llms/base_llm.py)
- [Task execution API](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/src/crewai/task.py)
- [Flow runtime and decorators](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/src/crewai/flow/flow.py)
- [Telemetry controls](https://github.com/crewAIInc/crewAI#telemetry)

## Limits and next milestones

The current complete suite passes **98 tests**. Reproduce the mock evaluation:

```sh
.venv/bin/python -m operations_agent.evaluation --output evaluation/mock_report.json
```

This command currently exits **1** because it measures one known extraction
limitation; it does not silently mark that case passed. Measured known-field
accuracy is 131/140 (93.57%); all 17 cases preserve the pipeline integrity checks.
These are deterministic mock results, not live AI accuracy. See the
[full evaluation report](../evaluation/README.md) for unresolved-field metrics,
denominators, the failing example and limitations. No live model was evaluated.

This is a controlled workflow with one bounded review agent, not an autonomous
multi-agent financial system. All records
remain pending human review, including valid ones. There is no approval action,
persistent database, UI, email sending, payment execution, or export.

Duplicate history covers one batch, including invalid records, using trimmed,
case-insensitive vendor and invoice identifiers. Monetary policy supports at most
two decimal places and amounts up to one trillion. Demo currencies are USD, EUR,
GBP, and INR; this is not complete international currency support. UUID record
identifiers change per run. Use synthetic data only.

Next stages include evaluating a configured live extractor on synthetic inputs,
explicit human review, persistence, and approved exports.
No database or real email, accounting, or payment connection is included.
