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

## The per-item protocol (F1 turn-based, owner 2026-07-29)

The driver tracks FOUR element states (owner's decree) and verifies
every step — it never assumes: the composer TEXT, the SEND–BUSY
button, the last SENT user turn, and the last IMAGE. Everything
after a send is judged against a pre-submit `Baseline` snapshot
(assistant-turn count + last generated image src), which makes
"grab the last visible image" — the duplicate-save root cause —
impossible.

```
BEFORE SEND: snapshot baseline; busy still present -> wait grace,
             then REFRESH (never send over a busy composer)
TYPE:        clear only a NON-empty composer; insert; VERIFY the
             composer holds our prompt (one retype, then loud fail)
SEND:        click; CONFIRM: composer emptied AND our text is the
             newest USER turn (fallback when user_turn selectors
             match nothing: composer empty + busy present, logged)
AWAIT:       done = a NEW assistant turn holding a loaded image
             whose src differs from the baseline's — even if the
             busy button is stuck; text answers classify via
             markers; unknown text -> NoImage(had_text=True)
EXTRACT:     bytes ONLY from that new turn's image
```

1. `submit_prompt(prompt, log=print)` — `_ensure_ready` (stuck-busy
   guard) → `capture_baseline()` → `_paste_and_send` →
   `_confirm_sent`. EVERY DOM interaction is preceded by
   `_hesitate()` — a random human-like pause from the config's
   action-delay range, so nothing ever fires machine-instant. The
   typing body lives in `_type_into_box(prompt)` (clears the box
   ONLY when it holds text, verifies the composer really holds the
   prompt via `_composer_holds`, one silent retype then loud
   `DriverError`); the locate + click of the send button lives in
   `_click_send(prompt, log)`; `_paste_and_send(prompt, log)` chains
   the two. `_confirm_sent` polls up to `send_confirm_timeout_s`
   for "composer empty AND our text visible as the newest user turn"
   (`SiteConfig.user_turn`), retrying the send once at half the
   window; an unconfirmable send raises loudly — the runner never
   proceeds on an unsent prompt.

   **Send-button reload recovery** (owner 2026-07-21, config
   `SEND_RELOAD_RECOVERY`, default on): a real run's exact failure —
   "no selector for the send button matched within 10s ... site
   stopped" — was fixed by nothing more than a manual page refresh.
   `_click_send` now does that refresh itself: when (and ONLY when)
   the send-button lookup raises `SelectorRot` — never any other
   selector miss (prompt box, busy signal, response image, ...) — it
   calls `page.reload()`, re-runs `_type_into_box(prompt)` (the reload
   wipes the composer's unsent text, so the prompt MUST be re-pasted),
   and retries the send-button lookup exactly ONCE more. A second miss
   raises `SelectorRot` same as always — the recovery is a single
   extra attempt, never a retry loop. `submit_with_image`'s prompt
   goes through the same `_paste_and_send`, so it gets the same
   recovery; note that a reload there would also drop the just-attached
   image (no re-attach step exists) — an acceptable edge gap.
   `runner.py`'s `submit_prompt` call site
   does not pass its own `log` through (the shared `driver` duck-type
   is also `ApiImageAdapter` in `gui/__init__.py`, whose `submit_prompt`
   takes no `log` parameter and is out of scope to change here) — the
   recovery message falls back to `log`'s own default (`print`), same
   as every other driver method's default-logging pattern.
1b. `submit_with_image(image_path, prompt)` — **image + text submit**
   (owner 2026-07-23), used BOTH by input-image sheet entries (the
   `← \`ref\`` reference photo — "put THIS character into that scene")
   and by WEBSITE FIX (re-attaching a flagged output for a focused
   correction); the prompt text carries the intent, the mechanics are
   one. Acts like a PERSON: walk `attach_menu_path` — EXPAND the "+"
   menu, then click the add-image option (never a hidden upload item
   directly) — each step `_hesitate()`-paced. Then attach the file: if
   the site exposes `file_input` (ChatGPT's `#upload-photos`),
   `set_input_files` on it directly (no OS dialog; the lookup does not
   require visibility, unlike every other selector here); else (Gemini)
   the option opens the OS dialog, caught with `page.expect_file_chooser()`.
   Then WAIT for the composer's `attach_preview` (up to
   `image_ready_timeout_s`) so the prompt never sends ahead of the
   image, then the SAME `_paste_and_send(prompt)` `submit_prompt` uses.
   Raises `AttachNotConfigured` immediately — before touching the page
   at all — while the site's `attach_menu_path` is empty. Only SUBMITS
   — the caller awaits the done edge and reads the image back with the
   SAME `await_done`/`extract_image` below, unchanged.
2. `await_done(log)` — waits for OUR RESULT, not for the button: the
   old "stop button disappears" done edge stalled forever on ChatGPT's
   stuck button and could not tell our generation from a leftover one.
   Now each poll (bounded by the hard `generation_timeout_s`) looks
   for an assistant turn NEWER than the baseline: a loaded image with
   a fresh src = done (even mid-stuck-button); turn text is scanned by
   `_check_image_failed(text)` (BUG 3 — ChatGPT's "Image generation
   failed" / "something seems to have gone wrong" faces, raised
   immediately, both riding the runner's recovery ladder) and
   `_check_markers(text)` (refusal/quota); final text with NO image
   and the busy signal gone raises `NoImage(had_text=True)`; nothing
   new + no busy signal past `busy_appear_timeout_s` raises
   `NoImage(had_text=False)` (the one nudge-eligible case).
3. `click_error_retry(log) -> bool` — the first rung of that ladder:
   click the site's native Retry button (`image_error_retry_button`,
   ChatGPT's `regenerate-thread-error-button`) if it has one for this
   state and it is present; True when clicked, False otherwise (no such
   selector, or not on the page right now). Never loud — a missing
   button is a normal branch.
4. `refresh(log)` — reload the page and wait for the composer back (a
   last-resort ladder rung): the login lives in the profile on disk, so
   the reload keeps the session; only the wedged page state is dropped.
2b. `new_chat(log)` — clicks the sidebar's New-chat control (config
   selectors, captured live 2026-07-18) and waits for the fresh
   composer; the callers use it between collections/folder groups
   when the option is on, and treat a failure as loud-but-not-fatal.
3. `extract_image() -> bytes` — the loaded, non-placeholder `<img>`
   of OUR new turn ONLY (src must differ from the baseline's last
   image — never "the last visible image on the page"), read in-page
   CANVAS-FIRST (`drawImage` + `toDataURL`): site CSP (Gemini)
   blocks `fetch()` of `blob:` srcs, while a canvas needs no request
   and always yields real PNG bytes; `fetch()` stays as the fallback.
   `click_error_retry` re-anchors the baseline one turn back (the
   native Retry regenerates IN PLACE), and `new_chat` clears it.

All required-element lookups poll up to the selector timeout before
failing loudly — SPAs morph elements a beat after input events (the
ChatGPT composer button turns into its send state only once the
pasted text lands).

## Failure taxonomy (all loud, root Rule #1)

- `SelectorRot` — no fallback selector matched; the site reskinned,
  fix the config block. EXCEPTION: a `SelectorRot` on the send button
  specifically is not immediately loud — `_click_send` first tries
  the one-time reload recovery above (`SEND_RELOAD_RECOVERY`); only a
  SECOND miss (post-reload) raises it for real.
- `ItemRefused` — the response matches a refusal marker: the runner
  reports the item and continues with the rest. Carries a `category`
  naming the refusal SCENARIO it matched (owner 2026-07-23) — the keys
  of the site's `refusal_markers` (`REFUSAL_SAFETY` / `REFUSAL_COPYRIGHT`)
  — so the runner picks the matching safer-retry preamble
  (`RETRY_PREAMBLES`): the allegory reframing for a safety block, the
  homage reframing for a copyright "third-party content" block. Marker
  categories are checked MOST-SPECIFIC-FIRST (the copyright message also
  contains generic safety substrings, so copyright is matched before
  safety).
- `TerminalState` — the response matches a quota/rate-limit marker:
  the whole site stops, never blind-retried. Carries
  `retry_after_s: float | None` — the wait the site itself named
  ("limit resets in 27 minutes"), parsed via the config's
  `QUOTA_RESET_PATTERNS` (English and Serbian phrasings); `None`
  when the message carried no parseable time. The runner logs it
  and re-raises the exception unchanged so the GUI/CLI read it too.
- `GenerationTimeout` — no result for our turn inside the hard cap.
- `NoImage` — a `DriverError` subclass for "our turn holds no image
  and its text matches NO known marker". **F1 (owner 2026-07-29):
  carries `had_text`.** `had_text=True` = the model ANSWERED with
  unrecognized text — the runner LOUD-SKIPS the item and NEVER sends
  the continue nudge (the market-scene incident: a nudge after an
  unmatched Gemini refusal produced a random unrelated image that
  was saved under the item's name). `had_text=False` = a truly
  empty/interrupted answer — the one case where a single
  `CONTINUE_NUDGE` is allowed; if the nudge also yields `NoImage`,
  the item is loud-skipped. `NoImage` no longer stops the site.

While waiting for the result `<img>`, the new turn's text is checked
every poll, so refusals raise in seconds instead of burning the
image timeout.
- `ImageGenFailed` — BUG 3 (owner 2026-07-21, second face 2026-07-23):
  ChatGPT's image tool failed outright while the busy/stop signal never
  clears, in one of two forms — its OWN "reply with 'retry'" text, or
  the generic "Hmm...something seems to have gone wrong." / "error on my
  side" error turn (which renders a native Retry button). Both match
  `image_failed_text_markers`. Distinct from `NoImage` (matches NO known
  marker — an unknown DOM state) and from `ItemRefused`/`TerminalState`
  (real refusal/quota markers); raised by `_check_image_failed()`,
  called from `await_done`'s "still generating" loop on every poll — a
  silent no-op wherever the site's `image_failed_text_markers` is empty
  (Gemini today). The runner catches it and walks a recovery LADDER
  (Retry button -> paced "retry" text -> escalation rounds of
  refresh + new session); the ladder re-raises only when every rung is
  spent, which stops the site.
- `ModelDegraded` — F2 (owner 2026-07-29): the site's degradation
  banner is up (Gemini's "Limit reached. Continuing with Flash-Lite.",
  `SiteConfig.degrade_banner`) and OUR turn produced no image. Checked
  BEFORE the quota markers (the banner's companion text also matches
  them). Carries `retry_after_s` parsed from the banner's own absolute
  phrasing ("on Jul 25 at 2:18 PM"). The runner asks the configured
  choice (`on_degrade`): "continue" = loud per-item skip, run stays
  alive on the weaker model; "wait" (and the CLI default) = re-raised
  as `TerminalState` (auto-restart at the reset).
- `AttachNotConfigured` — `submit_with_image` (image + text) is
  disabled for this site because `attach_menu_path` is empty in
  `SITES`. Used by both input-image entries and WEBSITE FIX. Raised
  immediately, before `submit_with_image` touches the page at all —
  never a guessed selector. (Both sites ship configured today, owner
  captures 2026-07-23.)
- `DriverError` — anything else the config block does not
  recognize, always with the response's opening text quoted. Both the
  CLI and the GUI catch `DriverError`, so `NoImage` (when a nudge does
  not recover it) is reported through that same path.

## Connections

### Uses
- [Config (subfolder)](config/___config.md) — `SiteConfig`, `Timing`,
  `MIN_IMAGE_PX`, `SEND_RELOAD_RECOVERY`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](runner.md) — per-item protocol
- [Main (CLI)](../main.md) — attach/close lifecycle

## Classes

### SiteDriver
`attach()` (find the tab by URL fragment; several tabs → the last
one), `submit_prompt()`, `submit_with_image()` (image + text, GATED by
`attach_menu_path` — see Failure taxonomy), `await_done()`,
`extract_image()`, `close()` (detaches; never closes the owner's
browser).

## Functions

- `sniff_format(data) -> str | None` — image format from magic
  bytes, so the runner can warn when saved bytes are not PNG.
