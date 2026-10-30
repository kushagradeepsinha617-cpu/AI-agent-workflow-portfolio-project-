# Pending-review workbench

The workbench puts the existing mock processing result into a local browser
interface: fields, evidence, unresolved information, validation errors, review
flags and the application-rendered summary. It is a viewer for pending records,
not an approval or payment workflow.

## Start and stop

Install the locked dependencies as described in the README. From the repository
root, run:

```sh
.venv/bin/python -m operations_agent.workbench --port 8765
```

The console prints the listening port. The server binds only to host `127.0.0.1`;
use a browser on that same machine with the printed port. No public hosting,
cloud port forwarding, or browser preview is configured by this command. This
cloud onboarding UI does not provide a workbench preview link. Stop the service
with Ctrl+C. A running service is not preserved by a Git commit or snapshot.

## Walkthrough

1. Choose a synthetic example, paste synthetic text, or load a small UTF-8 `.txt`
   file. PDF, scanned-image and OCR processing remain unsupported.
2. Optionally add email context and a list of known vendors. Each submission has
   its own validator instance; the viewer has no cross-submission duplicate history.
3. Process the invoice. The result shows extraction and validation separately,
   with the human decision still pending. Expand source evidence and the summary
   to inspect the reasoning inputs.
4. Edit the input and process again. Editing clears the displayed result so an
   earlier record is not presented as the result of new text.

Five examples come from the existing labelled synthetic dataset: valid invoice,
ambiguous date, conflicting email, incorrect total and unreadable text. The
server returns source documents, not expected answers. A wrong total is retained
as extracted and rejected by the existing validator. An ambiguous or conflicting
field stays null, with its evidence and review reason visible.

## Boundaries

- The endpoint always invokes `process_invoice(..., mode='mock')`. API credentials
  do not enable a paid request. There is no AI-mode switch in this viewer.
- There are no approve, reject, payment, email-sending or export routes/controls.
  Pipeline records must remain pending/awaiting review; a malformed or nonpending
  handoff is rejected with a processing error.
- Records are kept only in request/browser memory, not saved to a database or
  application history. Existing framework-generated local metadata is unchanged.
- The entire JSON request is limited to 256,000 bytes. The server uses an explicit
  route allowlist, strict JSON parsing, local Host/Origin checks and a 10-second
  body-read timeout. No arbitrary file path can be requested or submitted.
- Requests run serially because the existing CrewAI wrapper temporarily changes
  process-wide logging/stdout settings. This stdlib server is a local development
  interface, not an authenticated, multi-user or publicly hosted service.
- HTTP logs omit request paths and bodies. Processing errors use fixed messages;
  the existing extraction evidence is displayed only in the result.

The frontend uses text nodes for invoice values and citations. HTTP tests verify
that markup remains JSON data and does not enter the static HTML response;
they do not prove browser script execution behavior or comprehensive XSS safety.
Browser rendering, interactive behavior and accessibility checks are deferred.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -p test_workbench.py -v
.venv/bin/python -m unittest discover -s tests -v
node --check operations_agent/web/app.js
```

The workbench integration tests use loopback sockets and the real existing mock
pipeline. They require no external network, API keys or paid model calls. They
cover successful processing, unresolved fields, source conflicts, wrong totals,
request limits, malformed/duplicate JSON, foreign hosts/origins, disallowed paths,
attempted AI/decision overrides, and failed/nonpending processor responses.

The targeted HTTP suite now has **18 tests**; the full suite passed **120 tests**
on Linux, including five regression tests added in the full audit. The workbench
release originally had 17 HTTP tests and 115 total tests. JavaScript syntax checking passed. The documented
startup command was also exercised in its own process: assets/examples returned
HTTP 200, an incorrect total reached validation, and the service stopped cleanly.
Those checks do not establish visual rendering or complete browser interaction.

The original CLI, synthetic evaluation and reproducible demo remain available.
Neither their existing score nor the HTTP tests establishes live-model accuracy
or visual browser verification.
