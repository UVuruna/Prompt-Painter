# Driver Errors

**Script:** [Driver Errors (script)](../errors.py) ·
**Folder:** [driver/](../___driver.md)

## Purpose
The driver's typed error vocabulary — what the runner catches. Every
failure the driver can meet has its own class, so a caller decides by
TYPE rather than by parsing a message: a rotted selector is not a quota
wall, and a refused item is not a timeout.

A leaf module of its own so every mixin can raise these without
importing the package back.

## Failure taxonomy (all loud, the project's "Selectors fail LOUDLY" law)

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
Nothing — pure exception classes.

### Used by
Every module of this package, [Run Loop](../../__about/runner.md),
[Recovery Ladder](../../__about/recovery.md), the GUI's job mixins and
[Main (Entry Point)](../../../__about/main.md).

## Classes
`DriverError` and its ten subclasses — see the taxonomy above.
