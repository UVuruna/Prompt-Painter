# CDP Driver

**Script:** [CDP Driver (script)](../driver.py) ·
**Flow:** [diagram](../__flow/driver.md)

## Purpose

Drives the open, logged-in site tab. Chrome runs with
`--remote-debugging-port=9222` (see [Chrome Launcher](chrome.md) for
the dedicated automation profile); the driver attaches with
Playwright's `connect_over_cdp` — no extension, no OCR, no virtual
mice. It never clicks Download: the generated image's bytes are
fetched from the DOM (inside `page.evaluate`) and handed back for the
runner to save under the sheet's own name.

Already in the structure-law RATCHET as a god-file (1058 lines,
`config.SiteConfig`-driven protocol code) — documented normally per
the orchestrator's scope; a future split would carve it by
responsibility (submit / await / extract / recovery) rather than by
line count.

## The per-item protocol (F1 turn-based, owner 2026-07-29)

The driver tracks FOUR element states (owner's decree) and verifies
every step — it never assumes: the composer TEXT, the SEND–BUSY
button, the last SENT user turn, and the last IMAGE. Everything
after a send is judged against a pre-submit `Baseline` snapshot
(assistant-turn count + last generated image src + user-turn count),
which makes "grab the last visible image" — the duplicate-save root
cause — impossible. See the flow diagram for the full state machine.

**F1b — user-turn ANCHORING (owner 2026-08-04, the Padmé/Qui-Gon
incident; TEXT-FIRST since 2026-08-14, the SendVanished storm):** the
confirmed prompt's normalized head (`_sent_head`) AND full normalized
text (`_sent_norm`) become the result's ANCHOR. `_anchor_state()`
answers, on every poll, whether the newest user turn still reads as
OUR prompt: the head must be present, then the visible text must
agree with the full prompt for as far as both go, capped at
`ANCHOR_VERIFY_CHARS` (300) — the collapsed "Show more" view is a
prefix, and identical-head colored variants diverge inside that
window, so a DROPPED message still reads vanished. The USER-TURN
COUNT no longer votes: ChatGPT's new UI VIRTUALIZES turns out of the
DOM (`data-is-intersecting`, live CDP probe 2026-08-14), so the count
falls below the baseline on perfectly healthy sends — one such false
`SendVanished` fired every ~4 minutes through the 2026-08-14 run (the
Dashboard's "REFUSED" wall). The old count-then-head rule survives
only for flows with no recorded full prompt. `ok` → the accepted
result must
FOLLOW our own user turn in the DOM (`_follows`,
`compareDocumentPosition`) — the assistant-turn COUNT is ignored,
because a long chat VIRTUALIZES old turns out of the DOM and the
count can stand still while our answer is right there (the ChatGPT
retry whose refusal sat in the DOM for 4 minutes and still stopped
the site as "no new turn"); `vanished` (held `text_settle_s`) →
`SendVanished`; `unavailable` (no `user_turn` selector, nothing
confirmed) → the old count comparison stays as the fallback.

1. `submit_prompt(prompt, log=print)` — `_ensure_ready` (stuck-busy
   guard) → `capture_baseline()` → `_paste_and_send` →
   `_confirm_sent`. **The `log` is not optional in practice** (owner
   2026-08-04): `run_sheet` threads its own run log in, so every
   diagnostic below lands in the GUI and the report. It used to be
   omitted at the call site — the whole submit phase printed to stdout
   and a live ChatGPT run showed 7 unexplained SILENT minutes.

   **The pre-send busy wait** (`_ensure_ready`) never sends over a busy
   composer, and has its OWN budget `busy_stuck_timeout_s` (90s) —
   never the far longer `generation_timeout_s` it used to borrow (the
   7 minutes above). Two branches, both loud: a busy signal that
   `await_done` already saw STILL SET at the moment OUR image loaded is
   provably a stuck stop button (`_busy_known_stuck`) and the page is
   refreshed AT ONCE, no wait; any other busy signal may be a previous
   generation honestly finishing, so it gets the full budget (progress
   logged every `progress_log_interval_s`, with the budget named) and
   then a refresh. EVERY DOM interaction is preceded by
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
   selector miss — it calls `page.reload()`, re-runs
   `_type_into_box(prompt)` (the reload wipes the composer's unsent
   text), and retries the send-button lookup exactly ONCE more. A
   second miss raises `SelectorRot` same as always.
1b. `submit_with_image(image_path, prompt)` — **image + text submit**
   (owner 2026-07-23; MULTI faza 2 2026-08-03: `image_path` may be a
   LIST of resolved paths in the sheet's ← line order — all files ride
   ONE picker interaction, and a picker that refuses multiple files
   raises loudly rather than silently attaching fewer), used BOTH by
   input-image sheet entries (the `← \`ref\`` reference photo — "put
   THIS character into that scene") and by WEBSITE FIX (re-attaching a
   flagged output for a focused correction). Acts like a PERSON: walk
   `attach_menu_path` — EXPAND the "+" menu — each step
   `_hesitate()`-paced. Then attach the file(s): if the site exposes
   `file_input` (ChatGPT's `#upload-photos`) and it is ALREADY in the
   DOM once the menu is open, `set_input_files` on it directly and
   close the menu with Escape — the add-image ROW is deliberately NOT
   clicked, because ChatGPT's "Add photos & files" row IS the "Upload
   from computer" action and its click opens the NATIVE OS file dialog
   that Playwright cannot close (owner 2026-08-04: every attach left an
   Explorer window standing open beside the browser). Only a menu whose
   input renders lazily falls back to clicking the row — wrapped in
   `expect_file_chooser()` so a dialog that does open is consumed, with
   a second fallback to the revealed input on chooser timeout. Gemini
   (no `file_input`) keeps the plain chooser-interception path. Then WAIT
   for the composer's `attach_preview` before sending. Raises
   `AttachNotConfigured` immediately while the site's
   `attach_menu_path` is empty. A send-button reload recovery for
   this path RE-ATTACHES the image(s) before re-typing (a `reload()`
   drops the attachment too).
2. `await_done(log)` — waits for OUR RESULT, not for the button: the
   old "stop button disappears" done edge stalled forever on ChatGPT's
   stuck button and could not tell our generation from a leftover one.
   Each poll (bounded by the hard `generation_timeout_s`) looks for an
   assistant turn NEWER than the baseline: a loaded image with a fresh
   src = done (even mid-stuck-button — and when the busy signal IS
   still set at that moment, `_busy_known_stuck` records it so the NEXT
   submit refreshes instead of waiting it out); turn text is scanned for
   image-failed / refusal / quota markers; final text with NO image
   and the busy signal gone raises `NoImage(had_text=True)`; nothing
   new + no busy signal past `busy_appear_timeout_s` raises
   `NoImage(had_text=False)` (the one nudge-eligible case) with the
   REAL elapsed time in its message; our confirmed user turn GONE
   from the chat (F1b, settled `text_settle_s`) raises
   `SendVanished`.
3. `click_error_retry(log) -> bool` — the first rung of the recovery
   ladder: click the site's native Retry button
   (`image_error_retry_button`) if present; True when clicked. Never
   loud — a missing button is a normal branch.
4. `refresh(log)` — reload the page and wait for the composer back (a
   last-resort ladder rung); the login lives in the profile on disk. A
   composer that does not come back in time earns ONE more reload with
   a doubled budget (owner 2026-08-11, the 14:52:32 stop: a single slow
   reload ended a ChatGPT run at 38/69 collections) — a composer that
   is gone after that is still loud.
2b. `new_chat(log)` — clicks the sidebar's New-chat control and waits
   for the fresh composer; re-anchors the baseline to nothing (a fresh
   conversation restarts turn numbering).
3. `extract_image() -> bytes` — the loaded, non-placeholder `<img>` of
   OUR new turn ONLY (src must differ from the baseline's last image),
   read in-page CANVAS-FIRST (`drawImage` + `toDataURL`: site CSP
   blocks `fetch()` of `blob:` srcs on Gemini, while a canvas needs no
   request); `fetch()` stays as the fallback. When BOTH in-page paths
   fail, `_fetch_via_context` pulls the bytes over the browser
   CONTEXT's request API — outside the page, so no CORS applies, and
   carrying the context's cookies (owner 2026-08-11, the 16:32:13 stop:
   Gemini began serving results from `lh3.googleusercontent.com`
   instead of a `blob:` src, which taints the canvas AND fails the
   fetch; the raw error killed the whole site). Its own failure is a
   classified `NoImage` — a per-item skip, never an unhandled crash —
   and bytes that are not an image are refused, never saved.

All required-element lookups poll up to the selector timeout before
failing loudly — SPAs morph elements a beat after input events.

## Failure taxonomy (all loud, root Rule #1)

- `SelectorRot` — no fallback selector matched; the site reskinned,
  fix the config block. EXCEPTION: a `SelectorRot` on the send button
  specifically first tries the one-time reload recovery above; only a
  SECOND miss raises it for real.
- `ItemRefused` — the response matches a refusal marker: the runner
  reports the item and continues with the rest. Carries a `category`
  naming the refusal SCENARIO it matched (`REFUSAL_SAFETY` /
  `REFUSAL_COPYRIGHT`) so the runner picks the matching safer-retry
  preamble (`RETRY_PREAMBLES`). Marker categories are checked
  MOST-SPECIFIC-FIRST.
- `TerminalState` — the response matches a quota/rate-limit marker:
  the whole site stops, never blind-retried. Carries
  `retry_after_s: float | None` (parsed via `QUOTA_RESET_PATTERNS`,
  English and Serbian phrasings).
- `GenerationTimeout` — no result for our turn inside the hard cap.
- `NoImage` — a `DriverError` subclass for "our turn holds no image
  and its text matches NO known marker". Carries `had_text`.
  `had_text=True` = the model ANSWERED with unrecognized text — the
  runner LOUD-SKIPS the item and NEVER sends the continue nudge (the
  market-scene incident). `had_text=False` = a truly empty/interrupted
  answer — the one case where a single `CONTINUE_NUDGE` is allowed.
  `NoImage` no longer stops the site.
- `SendVanished` (F1b, owner 2026-08-04) — our CONFIRMED user turn is
  no longer in the conversation: the site dropped the message after
  `_confirm_sent` passed. In the live incident Gemini silently deleted
  the sent Padmé prompt; the old "nothing happened" verdict then
  allowed the content-blind continue nudge, Gemini REGENERATED THE
  PREVIOUS request, and a Qui-Gon badge was saved as
  `Padme_v3_gem.png`. The runner re-sends the item's OWN prompt (one
  try), never the nudge; a second vanish is a loud per-item skip.
- `ImageGenFailed` — ChatGPT's image tool failed outright while the
  busy/stop signal never clears, in one of two forms — its own
  "reply with 'retry'" text, or the generic "Hmm...something seems to
  have gone wrong." error turn (which renders a native Retry button).
  Both match `image_failed_text_markers`. A THIRD face (owner
  2026-08-11) carries the wording "Something went wrong. Please try
  again." and renders INSIDE the user turn, creating no assistant turn
  at all — no text scan can reach it, so the item burned the full
  `generation_timeout_s` (420s per occurrence in the live run). It is
  detected STRUCTURALLY by `_thread_error_risen()`: the count of the
  site's Retry buttons RISING above `Baseline.error_turn_count`. The
  verdict is a count rise and never mere presence — an error turn from
  an earlier item stays in the chat, and treating that as ours would
  fail every later item. SOFTENED 2026-08-14 (the Zealandia incident):
  the banner can now coexist with a DELIVERED image — ChatGPT showed
  the error and still rendered the globe in the same turn, and the old
  instant raise made the ladder send "retry" while the finished image
  sat unread. Now the IMAGE wins (checked first on every poll of
  `await_done`); the risen error becomes `ImageGenFailed` only after
  it holds `image_ready_timeout_s` with no image, and while it is
  pending the quiet no-turn wait never falls through to the
  nudge-eligible `NoImage`. `_check_image_failed()` (text markers)
  still raises directly — silent no-ops wherever the site's
  `image_failed_text_markers` / `image_error_retry_button` is empty
  (Gemini today). The runner
  catches it and walks a recovery LADDER (Retry button → paced "retry"
  text → escalation rounds of refresh + new session); the ladder
  re-raises only when every rung is spent, which stops the site.
- `SendNotConfirmed` (owner 2026-08-11, the 17:10:16 stop) — the
  prompt never became a user turn: the composer still holds the text
  and nothing was submitted. A PER-ITEM verdict — the send provably
  did NOT take, so nothing is half-generated and re-sending our own
  prompt is safe (it rides `SendVanished`'s handler). It was a bare
  `DriverError` until now, so one unaccepted send ended a Gemini run
  at 39/69 collections.
- `ModelDegraded` — the site's degradation banner is up (Gemini's
  "Limit reached. Continuing with Flash-Lite.", `SiteConfig.
  degrade_banner`) and OUR turn produced no image. Checked BEFORE the
  quota markers (the banner's companion text also matches them).
  Carries `retry_after_s` parsed from the banner's own absolute
  phrasing. The runner asks the configured choice (`on_degrade`):
  "continue" = loud per-item skip, run stays alive on the weaker
  model; "wait" (and the CLI default) = re-raised as `TerminalState`
  (auto-restart at the reset). `degrade_banner_text()` is a
  non-raising probe of the SAME banner, used AFTER a save (the image
  can arrive even while the banner is up).
- `AttachNotConfigured` — `submit_with_image` is disabled for this
  site because `attach_menu_path` is empty in `SITES`. Raised
  immediately, before touching the page at all.
- `DriverError` — anything else the config block does not recognize,
  always with the response's opening text quoted.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `SiteConfig`,
  `Timing`, `MIN_IMAGE_PX`, `SEND_RELOAD_RECOVERY`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](runner.md) — per-item protocol
- [Main (Entry Point)](../../__about/main.md) — attach/close lifecycle

## Classes

### SiteDriver
`attach()` (find the tab by URL fragment; several tabs → the last
one; a MISSING tab is opened by the driver itself — the caller has
already ensured Chrome via [Chrome Launcher](chrome.md)'s
`ensure_chrome`), `wait_for_login()` (poll for the composer while the
owner logs in by hand — status every 15 s, loud after
`login_wait_timeout_s`), `submit_prompt()`, `submit_with_image()`
(image + text, GATED by `attach_menu_path`), `await_done()`,
`extract_image()`, `close()` (detaches; never closes the owner's
browser).

## Functions

- `sniff_format(data) -> str | None` — image format from magic
  bytes, so the runner can warn when saved bytes are not PNG.
- `normalize_text(text) -> str` — whitespace-collapsed, lowercased
  text for the composer/user-turn DOM comparisons (ProseMirror/Quill
  editors reflow whitespace and newlines).

## 2026-08-11 — transcript support

- `last_response_text` — the FULL text of the LAST assistant answer
  the driver read (set in `await_done`/`extract_image`/`ask_text`,
  reset at `capture_baseline` so a previous item's text never poses as
  the current one's). The exceptions truncate text for their messages;
  the transcript log ([Transcript](transcript.md)) reads this instead.
- `ask_text(question, log) -> str` — the refusal diagnostic: send a
  TEXT-ONLY question and return the answer's full text. No image
  expected and NO marker classification (the site's explanation of a
  refusal legitimately contains the very words the markers match).
  Done = newest assistant turn's text stable for `text_settle_s` with
  the busy signal gone; returns whatever arrived by
  `generation_timeout_s` ("" = nothing).

### 2026-08-11c — the ask_text anchor fallback (owner-approved)
When the deadline passes with nothing ANCHORED (a vanished composer
breaks the anchor while the answer renders anyway — the Obi-Wan case),
`ask_text` reads the LAST assistant turn via `_last_turn_text_any()`
(anchor/baseline ignored) and returns it IF it differs from the text
that stood there BEFORE the question — so a still-visible refusal
never poses as its own diagnosis. `ask_used_fallback` flags the lower
confidence; the runner writes the transcript row as
`logged (anchor=fallback)`. Acceptable only for diagnostics — a
mis-attributed answer is a mislabeled log line, never a saved image.
