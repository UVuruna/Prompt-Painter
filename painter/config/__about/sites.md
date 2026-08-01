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
