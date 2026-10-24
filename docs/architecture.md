# Architecture and decision boundaries

The front-page diagram shows the flow. This page explains why its boundaries
exist and what they currently establish.

| Component | Owns | Must not do |
|---|---|---|
| Mock/AI extractor | Propose source-backed fields and report uncertainty | Invent absent facts, repair arithmetic, approve |
| Deterministic validator | Required fields, types, dates, amounts, currency and duplicates | Guess document meaning, approve |
| CrewAI Flow | Sequence steps, retain state, handle component failures | Hide uncertainty or treat execution success as approval |
| Review Agent + Task | Return references to the application's existing findings | Supply new invoice facts, prose, decisions or tool calls |
| Summary renderer | Present canonical fields, evidence, issues and errors | Treat an agent response as authority |
| Evaluation runner | Compare actual behavior with independent synthetic labels | Claim mock results measure a live model |
| JSONL event sink | Record stage metadata, counts and allowlisted codes | Record source content, credentials or raw exceptions |

## Why validation is deterministic

The business rules are explicit. Subtotal plus tax must equal total; a due date
cannot precede an invoice date; duplicate identity uses normalized vendor and
invoice identifiers. These checks need predictable software, not model judgment.
`Decimal` avoids binary floating-point rounding, and a private arithmetic context
prevents another component's precision settings from changing validation results.

The validator receives extracted strings and converts supported dates and money
into typed values. Missing or invalid values do not become fabricated substitutes.
Source extraction and validation are separate: an invoice with an incorrect total
can be successfully extracted and still fail validation.

## Why extraction can remain uncertain

A slash date such as `03/04/2026` has more than one interpretation without locale
context. Conflicting invoice/email totals also lack a justified single answer.
The system retains evidence and leaves these fields null. Missing, uncertain and
conflicting fields have separate metadata rather than an invented confidence score.

The optional AI adapter requests structured output and checks it again locally.
It requires cited tokens to exist on source lines. This guards against unsupported
values, but cannot establish semantic correctness or find conflicts omitted by
the model. Its accuracy has not been evaluated with live calls.

## What CrewAI contributes

Real `Flow` decorators coordinate extraction, validation and review preparation.
Structured state retains intermediate results and stage failures. One real
`Agent` and `Task` execute the review handoff using a deterministic `BaseLLM`
stub. The stub is not an offline AI model.

The task must return each supplied finding reference exactly once. Application
code rejects missing, duplicate or invented references and renders facts in a
stable order. A malformed result or task failure uses a deterministic fallback
summary and exposes `review_agent_task_failed`. No extraction or validation rerun
is needed just because presentation failed.

Ordinary Python functions would be simpler for this entire fixed workflow. CrewAI
is used to demonstrate an explicit framework integration and a constrained agent
boundary; it does not make the arithmetic better or add financial expertise.
Adding separate validation or risk LLM agents would duplicate existing rules.

## Human control and failure behavior

The current application prepares records for review. It does not implement the
human approval interface yet. Every processed record has `human_decision: pending`
and `processing_status: awaiting_review`, including valid and failed records.
Neither CLI mode exposes a decision-changing or payment operation.

| Situation | Result |
|---|---|
| Missing, uncertain or conflicting extraction | Null field, retained metadata, validation error and review flag |
| Wrong total | Extracted amount retained; validator reports `inconsistent_total` |
| Extractor raises or returns a malformed handoff | Failed extraction and a visible workflow issue |
| Validator fails to execute | Validation is `unavailable`, never silently valid |
| Review model/task fails | Existing facts retained; fallback summary and workflow issue |
| Log write fails | Processing continues; `observability_failed` is visible in the returned record |

## Runtime trade-offs

The review Task executes directly inside the Flow. Instantiating CrewAI's `Crew`
would create its SQLite replay storage, so this project avoids that class. Tests
block SQLite, DNS and network connections during a complete clean mock run.

CrewAI 1.15.30 also initializes a credential directory during import. The pinned
adapter redirects that generated local metadata to ignored `local-data/crewai`
through one inspected private method. Telemetry and tracing are disabled. This
compatibility override must be revisited when upgrading CrewAI.

The serial runner temporarily captures framework stdout and disables framework
logging, restoring logging afterward. It also sets framework environment options.
This is appropriate for the demonstrated CLI, not concurrent server requests.

The dependency lock includes CrewAI's substantial transitive dependencies. A
minimal production version might keep the fixed orchestration in ordinary Python.
There is no performance comparison establishing a framework advantage.
