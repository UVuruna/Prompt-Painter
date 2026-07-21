# CDP Driver

**Script:** [CDP Driver (script)](driver.py)

## Purpose
Drives the open, logged-in site tab. Chrome runs with
`--remote-debugging-port=9222` (see
[Chrome Launcher](chrome.md) for the dedicated automation
profile); the driver attaches with Playwright's `connect_over_cdp`
— no extension, no OCR, no virtual mice. It never clicks Download:
the generated
image's bytes are fetched from the DOM (inside `page.evaluate`) and
handed back for the runner to save under the sheet's own name.

## The per-item protocol

1. `submit_prompt(prompt)` — click the prompt box, select-all +
   delete, `insert_text` verbatim, click send. EVERY DOM
   interaction here (and in the send retry and `new_chat`) is
   preceded by `_hesitate()` — a random human-like pause from the
   config's action-delay range (owner's #8), so nothing ever fires
   machine-instant. This click/select-all/delete/insert/send body
   lives in a shared private `_paste_and_send(prompt)`;
   `submit_prompt` is a one-line call onto it.
1b. `submit_fix(image_path, prompt)` — **WEBSITE FIX** (GUI rework
   Phase 17, **GATED**): click the site's attach/upload control,
   `set_input_files(image_path)` on its file input (often
   hidden-by-design — this lookup does not require visibility, unlike
   every other selector here), a settle pause, then the SAME
   `_paste_and_send(prompt)` `submit_prompt` uses. Raises
   `FixNotConfigured` immediately — before touching the page at all —
   while the site's `attach_button`/`file_input` are empty (`SITES`'
   shipped default for BOTH chatgpt and gemini today; the OWNER must
   capture the live selectors first, the same way every other
   selector in this file was captured). Only SUBMITS the fix — the
   caller awaits the done edge and reads the corrected image back
   with the SAME `await_done`/`extract_image` below, unchanged.
2. `await_done(log)` — the done edge: the busy signal (stop button)
   must appear, then disappear, under the hard generation timeout;
   long waits log progress at the configured cadence.
2b. `new_chat(log)` — clicks the sidebar's New-chat control (config
   selectors, captured live 2026-07-18) and waits for the fresh
   composer; the callers use it between collections/folder groups
   when the option is on, and treat a failure as loud-but-not-fatal.
3. `extract_image() -> bytes` — the last loaded, non-placeholder
   `<img>` of the last response turn, read in-page CANVAS-FIRST
   (`drawImage` + `toDataURL`): site CSP (Gemini) blocks `fetch()`
   of `blob:` srcs, while a canvas needs no request and always
   yields real PNG bytes; `fetch()` stays as the fallback.

All required-element lookups poll up to the selector timeout before
failing loudly — SPAs morph elements a beat after input events (the
ChatGPT composer button turns into its send state only once the
pasted text lands).

## Failure taxonomy (all loud, root Rule #1)

- `SelectorRot` — no fallback selector matched; the site reskinned,
  fix the config block.
- `ItemRefused` — the response matches a SAFETY-refusal marker: the
  runner reports the item and continues with the rest.
- `TerminalState` — the response matches a quota/rate-limit marker:
  the whole site stops, never blind-retried. Carries
  `retry_after_s: float | None` — the wait the site itself named
  ("limit resets in 27 minutes"), parsed via the config's
  `QUOTA_RESET_PATTERNS` (English and Serbian phrasings); `None`
  when the message carried no parseable time. The runner logs it
  and re-raises the exception unchanged so the GUI/CLI read it too.
- `GenerationTimeout` — no done edge inside the hard cap.
- `NoImage` — a `DriverError` subclass for the "no image, unknown DOM
  state" case that `_raise_no_image` builds: either the busy signal
  never appeared after submit, or the done edge fired yet no image
  loaded and the answer text matches NO refusal/quota marker (the
  owner's recurring stuck-ChatGPT case — done edge fired, empty text).
  Distinct from the generic `DriverError` precisely so the runner can
  catch JUST this and send a one-shot **continue nudge**
  (`CONTINUE_NUDGE`) into the same chat before giving up; if the nudge
  does not recover it, `NoImage` propagates like any other
  `DriverError` and the site stops loudly. A matched marker still wins
  first — `_raise_no_image` calls `_check_markers()`, so a refusal /
  quota answer raises `ItemRefused` / `TerminalState` instead.

While waiting for the result `<img>`, the response text is checked
every poll, so refusals raise in seconds instead of burning the
image timeout.
- `FixNotConfigured` — GUI rework Phase 17: `submit_fix` (WEBSITE
  FIX) is disabled for this site because `attach_button`/`file_input`
  are empty in `SITES` — the shipped default for BOTH chatgpt and
  gemini until the owner captures the live selectors. Raised
  immediately, before `submit_fix` touches the page at all — never a
  guessed selector.
- `DriverError` — anything else the config block does not
  recognize, always with the response's opening text quoted. Both the
  CLI and the GUI catch `DriverError`, so `NoImage` (when a nudge does
  not recover it) is reported through that same path.

## Connections

### Uses
- [Config (subfolder)](config/___config.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](runner.md) — per-item protocol
- [Main (CLI)](../main.md) — attach/close lifecycle

## Classes

### SiteDriver
`attach()` (find the tab by URL fragment; several tabs → the last
one), `submit_prompt()`, `submit_fix()` (GATED — see Failure
taxonomy), `await_done()`, `extract_image()`, `close()` (detaches;
never closes the owner's browser).

## Functions

- `sniff_format(data) -> str | None` — image format from magic
  bytes, so the runner can warn when saved bytes are not PNG.
