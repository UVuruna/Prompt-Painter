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
   machine-instant.
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

While waiting for the result `<img>`, the response text is checked
every poll, so refusals raise in seconds instead of burning the
image timeout.
- `DriverError` — anything else the config block does not
  recognize, always with the response's opening text quoted.

## Connections

### Uses
- [Config](config.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](runner.md) — per-item protocol
- [Main (CLI)](../main.md) — attach/close lifecycle

## Classes

### SiteDriver
`attach()` (find the tab by URL fragment; several tabs → the last
one), `submit_prompt()`, `await_done()`, `extract_image()`,
`close()` (detaches; never closes the owner's browser).

## Functions

- `sniff_format(data) -> str | None` — image format from magic
  bytes, so the runner can warn when saved bytes are not PNG.
