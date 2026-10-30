# Capture ten screenshots locally

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

The capture script was syntax-checked here. It has **not been executed in a
browser in this session**, which has no callable browser-control/screenshot tool.
No screenshots are claimed to have been generated here.
