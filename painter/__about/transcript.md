# Transcript

**Script:** [Transcript (script)](../transcript.py)

## Purpose
`Transcript` — the per-site AI RESPONSE TRANSCRIPT (owner 2026-08-11):
every text the site answered, written down verbatim as the run meets
it, so a NEW unknown site state is diagnosed from the record instead
of by re-provoking the same failure live. Appends
`<out>/_state/<site>/transcript.jsonl` — one JSON object per line,
append-only, beside the report txt (out of the copy-ready tree). Each
row: `time`, `sheet`, `item`, `event` (`refused` / `retry_failed` /
`no_image` / `skipped` / `diagnosis` / `saved`), `raw_text` (the FULL
response text from `SiteDriver.last_response_text` — the exceptions
truncate it, the transcript never does), `matched` (the refusal
category that matched; `null` = the site said something our
recognition system does not know — the rows new markers are mined
from) and `action` (what the runner did).

## Connections

### Uses
- nothing beyond the standard library (`json`, `datetime`, `pathlib`)

### Used by
- [Run Loop](runner.md) — `run_sheet` builds ONE `Transcript` per run
  (always — it is diagnostics, cheap by construction) and records at
  every per-item outcome via its local `t_rec` helper
- [Config: AI](../config/__about/ai.md) — `TRANSCRIPT_FILENAME` names
  the file

## Classes

### Transcript
`record(event, sheet=, item=, raw_text=, matched=, action=, log=)`
appends one row. Best-effort BY DESIGN: a write failure is logged
loudly (`TRANSCRIPT WRITE FAILED`) and swallowed — the transcript is
diagnostics ABOUT the run, never allowed to kill the run (deliberate
scaling of No Error Masking).

## Design Decisions
- **JSONL, not the report txt.** The report is the owner's
  human-readable summary; the transcript is a machine-minable record
  (full texts, categories, null-matched rows) — different consumers,
  different files, same `_state/<site>/` home.
