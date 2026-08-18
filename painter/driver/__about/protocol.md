# Driver Protocol

**Script:** [Driver Protocol (script)](../protocol.py) ·
**Flow:** [diagram](../__flow/protocol.md) ·
**Folder:** [driver/](../___driver.md)

## Purpose
Putting ONE prompt into the composer and PROVING it was sent.

The driver tracks FOUR element states (owner's decree) and verifies
every step — it never assumes: the composer TEXT, the SEND–BUSY
button, the last SENT user turn, and the last IMAGE. Everything
after a send is judged against a pre-submit `Baseline` snapshot
(assistant-turn count + last generated image src + user-turn count),
which makes "grab the last visible image" — the duplicate-save root
cause — impossible. See the flow diagram for the full state machine.

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

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — `SEND_RELOAD_RECOVERY`
- [Driver Errors](errors.md) — `AttachNotConfigured`, `DriverError`,
  `SelectorRot`, `SendNotConfirmed`
- [Driver Values](values.md) — `Baseline`, `normalize_text`

### Used by
- [CDP Driver — the package's public surface](__init__.md) — mixed into
  `SiteDriver`
- [Run Loop](../../__about/runner.md) — per-item protocol

## Classes

### DriverProtocolMixin
`_hesitate`, `_composer_text`, `_busy`, `capture_baseline`,
`_ensure_ready`, `_type_into_box`, `_composer_holds`, `_click_send`,
`_paste_and_send`, `submit_prompt`, `_confirm_sent`,
`submit_with_image`, `_attach_image`. Never instantiated alone.
