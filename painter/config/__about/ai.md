# AI Config

**Script:** [AI Config (script)](../ai.py) ·
**Flow:** [diagram](../__flow/ai.md)

## Purpose

The largest config submodule (664 lines): prompt rules appended per
site, per-agent styles, safer-retry / continue-nudge / image-failed
recovery copy, and every constant behind the free Gemini API features
— the sheet generator, the image checker, API image generation, and
the Fixer AI (owner 2026-07-17 through 2026-07-29 F7).

## Connections

### Uses
- [Paths](paths.md) — `PROJECT_ROOT` (`SHEETS_DIR`)
- [Sites Config](sites.md) — `SITES` (lazy import inside
  `prompt_suffix`, to resolve `BACKGROUND_DEFAULT` per site)

### Used by
- [AI (subfolder)](../../ai/___ai.md) (`painter/ai/`) — the
  `GEMINI_*`/`AI_*` block, `SITES` re-send reverse map, `STATE_DIRNAME`
- [Run Loop](../../__about/runner.md) — `prompt_suffix`,
  `RETRY_PREAMBLES`, `CONTINUE_NUDGE`, `IMAGE_RETRY_NUDGE`,
  `IMAGE_FAILED_*`
- GUI (`gui/agent_panel.py`, `gui/api_panel.py`) — background/style/
  helper dropdowns, the Gemini API key wizard, the Fixer mode toggle
- Re-exported by [Config Package Index](__init__.md)

## Constants and Functions (by section)

**Prompt suffix — background rule + prompt helpers:**
- `BACKGROUND_DEFAULT`, `BACKGROUND_CUSTOM`, `BACKGROUND_CHOICES` —
  the background dropdown values (`_BACKGROUND_RULE` is the private
  dict backing the plain rule strings, not part of the public API)
- `PROMPT_HELPERS`, `HELPER_CHOICES`, `HELPER_DEFAULTS` — F7
  (2026-07-29): the old baked per-site laws became per-agent ON/OFF
  toggles (`no_mirror`, `no_empty_space`, `no_grainy`); defaults keep
  pre-F7 behaviour byte-identical
- `SITE_PROMPT_RULES` — legacy per-site table, EMPTY since F7; kept as
  the seam for any future truly-unswitchable site law

**Per-agent style clause:**
- `STYLES`, `STYLE_CHOICES`, `STYLE_DEFAULT` — 7 styles (`"None"`
  first), each clause appended at the very end of the suffix

**Prompt suffix assembly:**
- `prompt_suffix(site_key, background, style, helpers, custom_hex) ->
  str` — see [flow](../__flow/ai.md)

**Safer-retry preambles + continue nudge:**
- `SAFER_PREAMBLE`, `COPYRIGHT_PREAMBLE`, `RETRY_PREAMBLES` — keyed
  by refusal scenario (`REFUSAL_SAFETY`/`REFUSAL_COPYRIGHT` from
  [Sites Config](sites.md)); a category with no preamble gets no retry
- `CONTINUE_NUDGE` — the ChatGPT stall nudge (empty answer, no image)

**Image-generation-failed retry ladder (ChatGPT BUG 3):**
- `IMAGE_RETRY_NUDGE` — the literal `"retry"` word ChatGPT's own
  answer asks for
- `IMAGE_FAILED_RETRY_MAX`, `IMAGE_FAILED_RETRY_DELAY_RANGE_S` — up to
  3 resends, each preceded by a random 3-6 min wait
- `IMAGE_FAILED_ESCALATION_DELAYS_S` — 3 escalation rounds (refresh +
  new session + resend), ~12-15 min each; exhausting all rounds STOPS
  the site

**Gemini API — model names + endpoint:**
- `GEMINI_API_BASE` — the AI Studio REST base URL
- `GEMINI_TEXT_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_IMAGE_MODEL` —
  the `-latest` free-tier aliases (text/vision) and the paid image
  model (rotates as Google retires generations)
- `GEMINI_KEY_SETTING`, `AI_STUDIO_URL` — the `settings.json` key name
  and the wizard's key-page link

**Model discovery + call / retry tunables:**
- `MODELS_SETTING` — the `settings.json` per-purpose model override key
- `MODEL_PURPOSE_RANKING` — ordered substrings per purpose
  (image/vision/text), best first
- `AI_CALL_PAUSE_S`, `AI_TIMEOUT_S`, `AI_TEST_PROMPT` — free-tier
  pacing, HTTP timeout, the wizard's cheap test prompt
- `AI_TRANSIENT_STATUS`, `AI_RETRY_MAX`, `AI_RETRY_BACKOFF_S`,
  `AI_RETRY_MAX_WAIT_S` — which HTTP statuses retry and how

**API image quota markers:**
- `AI_IMAGE_QUOTA_MARKERS` — AND-groups of substrings that make a 429
  PERMANENT (`PaidFeatureRequired`) instead of transient

**API image generation job:**
- `AI_IMAGE_PROBE_PROMPT`, `AI_IMAGE_GATE_MESSAGE` — the "Check API
  access" probe prompt and the owner-facing gate message (reworded
  ACTIONABLE, faza 3 2026-08-03: Google's image free tier is
  literally 0 — the message now names the fix, billing on the key's
  AI Studio project)

**API image gen — model purpose hints (faza 3):**
- `MODEL_PURPOSE_HINTS`, `MODEL_HINT_UNKNOWN`, `model_hint(name)` —
  the curated "which model for what" one-liners under the API panel's
  Image dropdown; substring match, first wins, honest UNKNOWN for
  anything uncurated (never invented)

**AI sheet generator — prompts:**
- `AI_MAX_QUESTIONS`, `SHEETS_DIR` — the clarifying-poll cap and the
  AI-sheet save directory
- `AI_QUESTIONS_SYSTEM`, `AI_SHEET_SYSTEM`, `AI_SHEET_REQUEST`,
  `AI_REPAIR_PROMPT` — the two-call generation flow's system/user
  prompts, plus the one automatic repair round

**Image checker — copy:**
- `AI_FLAGS_FILENAME` — `ai_flags.json` under `<out>/_state/`
- `AI_CHECK_INSTRUCTIONS` — the banal-defects-only vision instruction
- `AI_CHECK_PROMPT_MATCH` — F6 (2026-07-29): the additional
  prompt-vs-image content-mismatch question, appended when the item's
  own sheet prompt is known

**Fixer AI — templates + mode:**
- `AI_FIX_NOTE` — the per-item re-send suffix naming the flaws
- `AI_FIX_PROMPT_WITH_DEFECTS`, `AI_FIX_PROMPT_NO_DEFECTS`,
  `AI_FIX_PROMPT_RAW_SUFFIX` — `build_fix_prompt`'s two templates plus
  the raw-report suffix
- `FIXER_MODE_API`, `FIXER_MODE_WEBSITE`, `FIXER_MODE_CHOICES` — the
  Fixer's dispatch mode (parallel API call vs. queued website resend)

**Model degradation:**
- `DEGRADE_ASK`, `DEGRADE_CONTINUE`, `DEGRADE_WAIT`, `DEGRADE_CHOICES`
  — F2 (2026-07-29): what a run does when Gemini's Flash-Lite
  degradation banner is up and no image comes

**Quota reset time — parser:**
- `QUOTA_RESET_PATTERNS` — relative-phrasing regexes ("in 27 minutes",
  Serbian "za 14 sati"), each mapped to a seconds-per-unit multiplier
- `parse_quota_reset(text) -> float | None` — see
  [flow](../__flow/ai.md). Falls back to the private
  `_parse_quota_reset_at`/`QUOTA_RESET_AT_PATTERN`/`_MONTHS` helpers
  for Gemini's ABSOLUTE reset-moment phrasing ("on Jul 25 at 2:18
  PM") — these three names are module-private in practice (leading
  underscore on the function, and `QUOTA_RESET_AT_PATTERN`/`_MONTHS`
  are not re-exported by [Config Package Index](__init__.md) even
  though they carry no underscore prefix themselves)
