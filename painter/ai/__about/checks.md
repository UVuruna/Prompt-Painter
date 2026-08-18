# Image Checker

**Script:** [Image Checker (script)](../checks.py) ·
**Flow:** [diagram](../__flow/checks.md)

## Purpose

The owner's #3: what a vision check ANSWERS and what the app does with
it — the strict response format, the fix prompt built from it, the
per-image driver both GUI callers share, and the plan for re-sending a
flagged image to the site that made it. Split out of the single-file
`painter/ai.py` (root Rule #20, 2026-07-30).

## Connections

### Uses
- [Gemini REST Client](client.md) — `check_image` (the default
  `check`), `model_for`, `AiError`
- [Flag Memory](flags.md) — `flag_key`, `record_flag`, `clear_flag`
- [Config (subfolder)](../../config/___config.md) — `AI_FIX_*`, `SITES`

### Used by
- [AI (subfolder)](../___ai.md) — `__init__.py` re-exports it
- [GUI (folder)](../../../gui/___gui.md) — the standalone AI-check
  job, the parallel per-item checker, the Fixer AI's prompt, and the
  re-send mapping

## Functions

- `parse_check_response(text) -> list[str]` — the strict format:
  `OK` → `[]`; `DEFECTS:` + dash lines → the list; anything else is
  a loud `AiError` (never guessed).
- `check_one_image(src, out_base, instructions, *, prompt=None,
  model=..., log, check=None) -> dict` — the pure per-image driver TWO
  independent GUI callers share (offline-testable — `check` defaults
  to this module's `check_image`, so a test injects a per-image mock):
  the standalone batch checker's worker loop and the SITE dashboard's
  parallel per-item checker. `prompt` passes straight through to
  `check` — but ONLY when not `None`, so a `check` double with no
  `prompt` parameter of its own (older tests, callers that never opt
  in) keeps working unchanged. Times the call, parses the answer,
  MERGES the flag (or CLEARS a fixed image's old one) and returns the
  row the panel renders: `{rel (=flag_key), kind ('flagged'/'ok'/
  'error'), defects, raw (verbatim), time (seconds)}`. A per-image
  `AiError` (HTTP after the retries, or a malformed answer) is
  CAUGHT and returned as an `error` row — loud in the log, never
  fatal; its `raw` is the model's answer when we got one (a parse
  failure) or the error text (an HTTP/network failure), so the viewer
  always shows what happened.
- `fix_note(defects)` — the re-send's per-item extra suffix
  (`AI_FIX_NOTE`, "; "-joined defects).
- `build_fix_prompt(defects, raw=None) -> str` (the Fixer AI) — the
  instruction sent ALONGSIDE a flagged image to `edit_image` (IMAGE
  FIX / the API-mode auto-fixer) or [CDP Driver](../../driver/___driver.md)'s
  `submit_with_image` (WEBSITE FIX). PURE — no I/O, offline-testable.
  Named `defects` become a bulleted "fix ONLY these, keep everything
  else as it is" instruction (`AI_FIX_PROMPT_WITH_DEFECTS`); an EMPTY
  list still returns a sensible, non-blank fallback
  (`AI_FIX_PROMPT_NO_DEFECTS`) rather than raising or returning `""`.
  `raw` — when given and non-blank — is appended VERBATIM after the
  instruction (`AI_FIX_PROMPT_RAW_SUFFIX`), never in place of it: the
  parsed bullets are the actionable part, the raw model response is
  grounding context alongside them.
- `drop_and_site_for(rel) -> (drop_path, site) | None` — the
  `config.dest_for` REVERSE: `<rest>/<File>[_vN]_gem|_gpt|_api.png` →
  `('assets/<rest>/<File>.png', site)` (the filename-suffix
  convention, DOMY RESTRUCTURE 2026-07-22; a `_vN` version sibling —
  the ticked-redo output — reverses to the SAME canonical drop as its
  master, so a flagged version re-sends through its own sheet entry
  and the redo lands as the NEXT version); the pre-RESTRUCTURE
  `<category>/<site>/<rest>` folder layout and legacy `<site>/<drop>`
  still reverse for old out/ trees; `None` when nothing names a
  generator.
- `plan_resend(flagged, drop_to_source) -> (plans, notes,
  unmatched)` — the whole re-send plan, pure and GUI-free:
  `plans[site][sheet-source]` is the drop set that site runs
  (`only=`), `notes[site][drop]` each item's fix note
  (`extra_suffix`), `unmatched` the `(key, reason)` pairs the caller
  logs loudly (no site in the path / not in any queued collection).

## Design Decisions
- **`check_one_image` is the pure seam.** The worker used to hold the
  per-image logic (key, time, parse, flag, emit) inline; extracting it
  makes the response↔image pairing testable WITHOUT a GUI and gives
  the raw/time one place to live.
- **The prompt-match clause is appended text, not a second call.**
  `check_image`/`check_one_image` still make ONE vision call per
  image — `AI_CHECK_PROMPT_MATCH` is glued onto whatever
  `instructions` the caller already built, and the model is told to
  report a content mismatch in the SAME `DEFECTS:` format
  (`parse_check_response` reads one strict shape, never two).
