# Full audit — October 30, 2026

Scope: validator, mock/AI extraction, CrewAI handoffs, CLI/file handling, HTTP
workbench contracts, JavaScript syntax, reproducible evaluation and documentation.
Synthetic data only; no paid calls, database or new features. UI redesign remains
paused. This is a bounded engineering audit, not proof that no bugs remain.

## Confirmed defects and fixes

- Invoice CLI logs could append to the invoice or email source itself. The
  evaluator guarded matching paths, but a hard link could bypass that guard and
  overwrite a dataset. Both commands now check resolved paths and existing file
  identity before opening outputs. Tests verify controlled exit 2 and unchanged
  source bytes, including hard links. This is a local CLI safeguard, not atomic
  protection against another process replacing files concurrently.
- The orchestration handoff accepted null extracted fields without explicit
  missing/uncertainty/conflict metadata. It now rejects the contradictory handoff
  as a controlled extraction failure and keeps the record pending for review.
- Evidence dataclasses with malformed members could reach the review summary;
  an unserializable value could also break its fallback. Source, line and token
  types are now checked before review. Tests cover malformed source/token values,
  boolean line numbers and zero line numbers. The final independent review found
  the same gap in uncertainty reasons and conflict lists; those metadata values
  are now checked too, with regression subcases in the same test.
- HTTP output checks allowed incomplete metadata to return status 200 even though
  the browser renderer required that metadata. The response contract now checks
  the lists, fields, evidence and review metadata before returning a record;
  malformed handoffs return a sanitized status 500 with a pending decision.
- Documentation had a stale "current 98 tests" statement and broad "no network"
  claims despite loopback HTTP tests. Counts and external-network wording are
  corrected. Historical checkpoint counts are retained where labelled as such.

Five regression test methods were added, with multiple independent subcases.
Each group failed against the previous implementation before its fix.
The financial validator and both extraction implementations were not rewritten.

## Actual verification

- Baseline suite before changes: 115 tests passed.
- Complete suite after fixes: 120 tests passed on Linux, Python 3.12.
- Locked installed dependencies: `uv pip check` passed.
- `node --check operations_agent/web/app.js` passed.
- A fresh workbench server served all three static assets and processed all five
  supplied examples over HTTP. All stayed pending, incorrect totals and conflicts
  remained visible, no workflow failed, and the server stopped cleanly.
- `scripts/demo.py` reproduced the saved checkpoint and exited 0.
- Standalone evaluation retains its expected exit 1 for `unsupported_prose`:
  131/140 known fields recovered, 16/17 quality passes, 17/17 integrity passes.

Reproduce from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/demo.py
.venv/bin/python -m operations_agent.evaluation --output local-data/audit-evaluation.json
node --check operations_agent/web/app.js
uv pip check --python .venv/bin/python
```

## Remaining limits

- OpenAI adapter tests use synthetic responses; CrewAI uses offline/scripted review
  models. No live-model accuracy or real-world invoice performance was measured.
- Evidence matching proves a token occurs on a cited line, not that its field
  assignment is correct or that every conflict was disclosed.
- This audit did not execute a browser or visually inspect the UI. HTTP checks
  and JavaScript parsing do not establish full interactive or accessibility quality.
- Native Windows runtime testing remains unverified here; dependency resolution
  for Windows was checked separately during the installation fix.
- Mock prose parsing remains deliberately narrow. No PDF/OCR, permanent history,
  cross-submission duplicate detection, decision controls or payment integrations.
- Loopback server and process-wide CrewAI wrapper are serial development tools,
  not an authenticated production service.
