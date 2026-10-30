# Capture ten screenshots locally

## Automatic video walkthrough

From the project folder in PowerShell, after updating with `git pull --ff-only`, run:

```powershell
uv run --no-project --python 3.12 --with playwright python scripts/capture_screenshots.py --record --start-server
```

This uses the project's installed `.venv` to start the workbench if needed, so a
second terminal is unnecessary. An already running server is reused and left
running; a server started by the runner is stopped when it exits.

The runner captures ten PNGs and a silent `workflow.webm` in the timestamped output
folder. It walks through valid, incorrect-total, ambiguous-date, conflicting-email
and unreadable examples, pausing on fields, warnings, evidence and the pending
decision. Allow about a minute plus loading/processing time. Reading pauses are
added to the recording; they are not performance measurements. It does not add
captions, narration or invented UI elements. This is a synthetic mock demonstration.

The video is WebM, not MP4. Review the result before sharing it. If your posting
platform requires MP4, convert it with your video editor. Chromium must first be
installed using the command below; your earlier successful install can be reused.
Partial videos after a failure are not labelled `workflow.webm`.

## Screenshots only

This optional runner operates on the same machine as the running workbench.
It captures the source and processed result for all five synthetic examples:
valid, ambiguous date, conflicting email, incorrect total and unreadable text.
Result screenshots include expanded evidence and review summaries. It checks
HTTP results, validation status and the pending boundary before saving results.
It uses an isolated Chromium session, not your personal browser profile.

Keep the workbench running. In a **second PowerShell window**, from the repository
folder, run each command separately:

```powershell
uv run --no-project --python 3.12 --with playwright python -m playwright install chromium
uv run --no-project --python 3.12 --with playwright python scripts/capture_screenshots.py
```

The first command downloads optional screenshot tooling and Chromium. It does not
change the application dependency lockfile or require an API key. The second
prints the output folder under `local-data/screenshots/<timestamp>/`. Open that
folder in File Explorer to view the ten PNGs. Screenshot folders are ignored by
Git. The script stops if processing or UI assertions fail; a partially populated
folder does not mean all ten captures succeeded.

The capture script and CLI options were syntax/help-checked here. Real loopback
checks verified the missing-server error, automatic startup, reuse without
stopping an existing server, and cleanup of the runner's child process.
The recording itself has **not been executed in a
browser in this session**, which has no callable browser-control/screenshot tool.
No screenshots are claimed to have been generated here.
