# Sites Config

**Script:** [Sites Config (script)](../sites.py) ·
**Flow:** [diagram](../__flow/sites.md)

## Purpose

Timing (every wait/pace, in seconds) and the per-site DOM selectors
the CDP driver watches — prompt box, send/busy/response/result
hooks, refusal/quota/image-failure text markers, and image-attach
selectors. Selectors rot with every site reskin: each DOM hook is a
tuple of fallbacks tried in order, and when none match the driver
FAILS LOUDLY (root Rule #1) instead of guessing.

## Connections

### Uses
Nothing at module scope — a leaf module.

### Used by
- [CDP Driver](../../__about/driver.md) — `SiteConfig`, `Timing`,
  `MIN_IMAGE_PX`, `SEND_RELOAD_RECOVERY`
- [Run Loop](../../__about/runner.md) — `TIMING`,
  `PAUSE_POLL_INTERVAL_S`
- [AI Config](ai.md) — `SITES` (lazy import inside `prompt_suffix`, to
  resolve `BACKGROUND_DEFAULT` per site)
- GUI — `SITES`, `TIMING`, `NEW_CHAT_CHOICES`
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Timing:**
- `Timing` — frozen dataclass of every wait/pace (action delay,
  selector/busy/generation/image-ready timeouts, send-confirm window,
  login-wait window, text-settle hold, poll interval, pacing range)
- `TIMING` — the module's one `Timing()` instance
- `PAUSE_POLL_INTERVAL_S` — the GUI Pause toggle's own wait-loop step
  (distinct from `Timing.pause_min_s`/`_max_s`, the between-prompts
  pacing wait)

**The pace** (owner 2026-08-07) — the between-images wait and the
action delay are protocol MECHANICS, so they left the GUI and live
here; the GUI kept ONE switch, **Polite pace**:
- `PACE_POLITE_S` = (12, 36) s — the switch ON
- `PACE_FAST_S` = (2, 13) s — the switch OFF
- `pace_range(polite)` — THE one authority both `_start_site` and the
  API job read, so the two jobs can never drift apart
- `PACE_POLITE_DEFAULT` — the switch's default (ON)
- `Timing.action_delay_min_s`/`_max_s` = 0.3 / 0.9 s — the hesitation
  between UI actions within one image, no longer owner-editable

The two ranges are not a speed dial but two PEOPLE (the owner's own
model, and why they may OVERLAP): polite = someone running this
alongside other work, fast = someone sitting on it, focused. Neither is
zero — a perfectly regular zero-gap cadence is the most recognisable
pattern there is, and the gap between requests is the largest part of
what keeps a run unremarkable (README → Honesty Notes). The site sees
pause + generation (~60 s), so the real cadence is ~72–96 s polite vs
~62–73 s fast; the daily image quota bites long before either becomes
a rate problem.
- `MIN_IMAGE_PX` — an `<img>` narrower than this is a placeholder
- `SEND_RELOAD_RECOVERY` — one page-reload retry when only the send
  button specifically cannot be found

**Refusal scenario categories:**
- `REFUSAL_SAFETY`, `REFUSAL_COPYRIGHT` — the two refusal categories;
  keys shared with `SiteConfig.refusal_markers` and `ai.RETRY_PREAMBLES`

**Site config — DOM hook schema:**
- `SiteConfig` — frozen dataclass: `prompt_box`, `send_button`,
  `busy_signal`, `response_container`, `result_image`,
  `refusal_markers` (dict keyed by scenario), `quota_text_markers`,
  `user_turn`, `degrade_banner`, `image_failed_text_markers`,
  `image_error_retry_button`, `new_chat`, the image-attach selectors
  (`attach_menu_path`, `file_input`, `attach_preview`)

**Sites — per-site DOM config + new-chat policy:**
- `SITES` — `{"chatgpt": SiteConfig(...), "gemini": SiteConfig(...)}`,
  each field verified against the live DOM by the owner (capture
  dates noted per selector)
- `NEW_CHAT_CHOICES` — `("off", "collection", "folder")`, when to open
  a fresh chat during a run

## 2026-08-11 — Serbian refusal markers for ChatGPT

ChatGPT also answers in the account's language (live capture, the Han
reference run): the same Serbian refusal stems Gemini already carried
("ne mogu da generi…", "ne mogu da kreiram", plus "ne mogu da
napravim") joined ChatGPT's `REFUSAL_SAFETY` group, so a Serbian
refusal gets the safer retry + the diagnostic question again.
