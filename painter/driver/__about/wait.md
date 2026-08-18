# Driver Wait

**Script:** [Driver Wait (script)](../wait.py) ·
**Flow:** [diagram](../__flow/wait.md) ·
**Folder:** [driver/](../___driver.md)

## Purpose
Waiting out one turn and reading its result: the turn-based DONE EDGE,
the F1b prompt ANCHOR, and the image bytes.

**F1b — user-turn ANCHORING (owner 2026-08-04, the Padmé/Qui-Gon
incident; TEXT-FIRST since 2026-08-14, the SendVanished storm):** the
confirmed prompt's normalized head (`_sent_head`) AND full normalized
text (`_sent_norm`) become the result's ANCHOR. `_anchor_state()`
answers, on every poll, whether the newest user turn still reads as
OUR prompt: the head must be present, then the visible text must
agree with the full prompt for as far as both go, capped at
`ANCHOR_VERIFY_CHARS` (300) — the collapsed "Show more" view is a
prefix, and identical-head colored variants diverge inside that
window, so a DROPPED message still reads vanished. The window is
anchored WHERE THE HEAD SITS in the turn's text, never at position 0
(2026-08-14, the continents Prompt+Image run: Gemini's `user-query`
renders the attached reference chip — the filename — BEFORE the
prompt, so a position-0 compare read every healthy attachment send as
vanished and re-sent it, burning quota on duplicate globes while the
Dashboard logged the whole sheet REFUSED). The USER-TURN
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

## Transcript support (2026-08-11)

- `last_response_text` — the FULL text of the LAST assistant answer
  the driver read (set in `await_done`/`extract_image`/`ask_text`,
  reset at `capture_baseline` so a previous item's text never poses as
  the current one's). The exceptions truncate text for their messages;
  the transcript log ([Transcript](../../__about/transcript.md)) reads this instead.
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

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — `MIN_IMAGE_PX`
- [Driver Errors](errors.md) — `DriverError`, `GenerationTimeout`,
  `ImageGenFailed`, `NoImage`, `SendVanished`
- [Driver Values](values.md) — `Baseline`, `normalize_text`,
  `sniff_format`
- [Driver Classify](classify.md) — the marker checks each poll runs

### Used by
- [CDP Driver — the package's public surface](__init__.md) — mixed into
  `SiteDriver`
- [Run Loop](../../__about/runner.md) — per-item protocol
- [Transcript](../../__about/transcript.md) — `last_response_text`

## Classes

### DriverWaitMixin
The F1 element-state readers (`_turns_count`, `_last_user_turn_text`,
`_user_turns_count`, `_last_user_turn_locator`, `_last_image_src`,
`_error_turns_count`), `await_done`, `extract_image`,
`_fetch_via_context`, `ask_text`, and the turn-scoping helpers
(`_require_baseline`, `_anchor_state`, `_follows`, `_new_turn`,
`_turn_image`, `_safe_text`, `_last_turn_text_any`). Never instantiated
alone.
