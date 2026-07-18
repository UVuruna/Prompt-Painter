# Config

**Script:** [Config (script)](config.py)

## Purpose
The single home of every tunable value (root Rule #4): connection
and Chrome launch, output layout, sheet-contract constants, the
background tool, timing, and the per-site DOM config blocks.
Selectors rot with every reskin — each DOM hook is a tuple of
fallbacks tried in order, and the driver fails loudly when none
match.

## Connections

### Uses
- Nothing (constants only).

### Used by
- [Sheet Parser](sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- [CDP Driver](driver.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- [Run Loop](runner.md) — `Timing`, `PROGRESS_SUFFIX`
- [Chrome Launcher](chrome.md) — `CDP_PORT`, `CHROME_CANDIDATES`,
  `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`
- [Postprocess](postprocess.md) — `CROP_MARGIN_PX`, `CROP_INK_ALPHA`,
  `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`,
  `SAFETY_MAX_REMOVE_FRAC`, `SAFETY_MAX_REMOVE_FRAC_WHITE`
- [Background Remover](bg_remove.md) — the same crop/cleanup
  constants (`content_bbox`, `clean_edge_halo`, `autocrop` defaults)
  plus `BLACK_VOID_MAX` and the two SAFETY guards, imported
  package-or-standalone
- [Upscale](upscale.md) — the `UPSCALE_*` block
- [Settings](settings.md) — `SETTINGS_PATH`
- [Main (Entry Point)](../main.md) / [GUI](../gui.md) — `CDP_URL`,
  `DEFAULT_OUT_DIR`, `SITES`, `TIMING`, `BACKGROUND_CHOICES`,
  `prompt_suffix`

## Values

- `CDP_PORT` / `CDP_URL` — Chrome's debug endpoint.
- `CHROME_CANDIDATES` — where chrome.exe usually lives.
- `CHROME_PROFILE_DIR` — the dedicated automation profile
  (`chrome-profile/`, gitignored; Chrome 136+ refuses CDP on the
  default profile). Log in once there; sessions persist.
- `DEFAULT_OUT_DIR`, `STATE_DIRNAME`, `PROGRESS_SUFFIX`,
  `REPORT_SUFFIX`, `dest_for(drop, site)` — the out/ tree MIRRORS
  DOMY's assets/: sheets carry site-agnostic
  `assets/<category>/<rest>` paths and `dest_for` injects the site
  after the category (`<out>/<category>/<site>/<rest>`); legacy
  relative drops keep `<out>/<site>/<drop>`. Run state + reports
  live under `<out>/_state/<site>/`, out of the copy-ready tree.
- `IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN` — the sheet contract's
  file-name rule and the REUSE / SUPERSEDED / DO-NOT-GENERATE
  marker regex.
- `CROP_MARGIN_PX`, `CROP_INK_ALPHA`, `CROP_MIN_INK_PX`,
  `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE` — the postprocess crop step
  (owner 2026-07-18, the OldAge.png case). The old single-threshold
  box (any pixel at alpha ≥ 8) was defeated by faint stray pixels
  hugging the border, so the crop trimmed almost nothing. Now the box
  is INK-BASED: a row/col counts as content only when it holds at
  least `CROP_MIN_INK_PX` pixels that are at least `CROP_INK_ALPHA`
  opaque, so a sparse faint line is ignored while wide soft regions
  register. Before cropping, `CLEAN_EDGE_ALPHA` + `CLEAN_EDGE_ENABLE`
  drive a CONSERVATIVE edge-halo cleanup: faint pixels connected to
  the image border (the visible stray line / halo) are zeroed, while
  interior soft edges — enclosed by the solid subject, never
  border-connected — are left alone. `CROP_MARGIN_PX` still pads the
  final box.
- `BLACK_VOID_MAX`, `SAFETY_MAX_REMOVE_FRAC`,
  `SAFETY_MAX_REMOVE_FRAC_WHITE` — the black-void removal + SAFETY guard
  (owner 2026-07-19, the bible/dark case). Brightness-keying cannot
  separate a DARK subject from a black background, so the old remover
  ate the dark frames of dark rondels. `BLACK_VOID_MAX` (14) is the
  void brightness ceiling for the BORDER-CONNECTED black removal (only
  the near-black touching the frame is cleared; interior enclosed dark
  regions stay opaque). The SAFETY guard aborts any removal that would
  clear too much (it ate the subject) — leaving the ORIGINAL untouched.
  It is PER PATH because the two paths' legit backgrounds differ wildly
  (measured over 531 real outputs): the BLACK guard
  `SAFETY_MAX_REMOVE_FRAC` (0.40) catches dark-rondel destruction
  (0.45+) while bright-on-black clears only ~0.24; the WHITE guard
  `SAFETY_MAX_REMOVE_FRAC_WHITE` (0.85) runs high because legit white
  backgrounds are large (real plates clear 0.33-0.57, median 0.44) —
  a single 0.40 would false-bail 58% of them, so white is guarded only
  against a catastrophic white-subject-eaten.
- `TOOLS_DIR`, `UPSCALE_DIR`, `UPSCALE_EXE_NAME`,
  `UPSCALE_ZIP_URL`, `UPSCALE_MODEL`, `UPSCALE_MIN_PX`,
  `UPSCALE_ASPECT_TOL` — the Real-ESRGAN upscaler: where the
  downloaded binary lives (`tools/`, gitignored), the official
  release zip, and the locked gating (owner 2026-07-18) — aspect
  W/H within `1 ± UPSCALE_ASPECT_TOL` AND a dimension below
  `UPSCALE_MIN_PX`.
- `ASPECT_TOL`, `ASPECT_DEFAULT_W`, `ASPECT_DEFAULT_H` — the
  [Change Aspect Ratio](aspect.md) batch deform tool: `ASPECT_TOL`
  (0.001) is how close an image's W/H must be to the target ratio to
  count as already-at-ratio (left byte-unchanged, no write);
  `ASPECT_DEFAULT_W`/`ASPECT_DEFAULT_H` (16 / 9) preselect the GUI's
  ratio prompt.
- `QUOTA_RESET_PATTERNS`, `parse_quota_reset(text) -> float | None`
  — the quota reset time (owner's #2): each pattern captures one
  number ("resets in 27 minutes", "in 14 hours", Serbian "za 27
  minuta" / "za 2 sata"); matches sum, no match → `None`. The
  driver stamps the result into `TerminalState.retry_after_s`.
- `SETTINGS_PATH` — the GUI settings JSON at the project root
  (gitignored).
- `THEMES`, `theme_pair(key)`, `status_pair(role)`, `SWITCH_*` — the
  GUI theming single source of truth (owner 2026-07-18). `THEMES`
  holds the two coordinated palettes, **night** (the built-in
  `darkly`, written out verbatim) and **day** (the custom
  `painter_day` light theme, the owner's warm-gold website palette),
  each with its ttkbootstrap theme name, customtkinter appearance
  mode, switch knob side, the 16 ttk colour keys and a `status`
  block (the semantic colours set per-widget: done / done_soft /
  advice / superseded / code_fg / btn_text). `theme_pair(key)`
  returns the `(day, night)` tuple every customtkinter colour kwarg
  passes so `set_appearance_mode()` flips them; `status_pair` does
  the same for the status block. The `SWITCH_*` constants are the
  Day/Night switch geometry (scaled from `SWITCH_H`) and its
  IMAGE-BASED art (owner 2026-07-18 — tkinter Canvas has no
  anti-aliasing, so the switch composites PIL images, not raw ovals):
  the two track pills are the owner's website SVGs
  (`SWITCH_TRACK_NIGHT_SVG` / `SWITCH_TRACK_DAY_SVG`, in
  `assets/icons/`), and the moon/sun knobs are PIL radial-gradient
  colours — silver moon (`SWITCH_MOON_CENTER`/`_EDGE`) + 3 craters,
  gold sun (`SWITCH_SUN_CENTER`/`_EDGE`) + a blurred glow
  (`SWITCH_SUN_GLOW*`) — rendered at `SWITCH_SUPERSAMPLE`x and
  LANCZOS-downscaled. This block is PURE hex/number data — no
  tkinter/ttkbootstrap/PIL import — so the engine and tests stay
  framework-free; [GUI](../gui.md) rasterizes it into the live art.
- `BACKGROUND_CHOICES`, `SITE_PROMPT_RULES`, `GEMINI_ASPECT_RULES`,
  `prompt_suffix(site_key, background, prompt_text)` — the rule
  block appended to every prompt: the chosen background (each
  site's dropdown defaults to its `default_background` — ChatGPT
  transparent, Gemini white) plus the site's forced laws (owner
  2026-07-17). Gemini's aspect law is picked FROM THE PROMPT:
  TALL/lancet prompts get tall portrait, everything else (badges,
  rondels, medallions) a perfect 1:1 square; plus NO reflections.
- `SAFER_PREAMBLE` — the allegory-framing note prepended on a
  one-shot safer retry after a SAFETY refusal (opt-in). An honest
  reframing of legitimate symbolic art (no real people, non-graphic),
  never a way to force disallowed content.
- `fmt_duration(seconds)`, `fmt_size(bytes)` — the short human
  formatters shared by the runner report and the GUI dashboard.
- `MIN_IMAGE_PX` — an `<img>` narrower than this is a placeholder.

## Classes

### Timing
All waits and paces in seconds: the human-like action delay
(`action_delay_min/max_s` — a random hesitation between click,
paste and send, like a person doing Ctrl+V then Enter; GUI-tunable),
the selector timeout (required elements poll instead of one-shot
lookups), busy-appear timeout with the send-retry interval (a
blocked send button is clicked again / Enter pressed until the busy
signal shows), the generation hard timeout, image-ready timeout,
poll step, progress-log cadence, and the polite pause between
prompts — a RANDOM duration drawn from `[pause_min_s, pause_max_s]`,
fractional seconds included.

### SiteConfig
One site's block: `url` (the tab the launcher opens),
`url_fragment` (finds the open tab), `default_background` (the
suffix key `auto` resolves to), `prompt_box`, `send_button`,
`busy_signal`
(visible only while generating — its disappearance is the done
edge), `response_container`, `result_image`, and
`refusal_text_markers` (the substrings that mark a no-image
response as terminal).

`SITES` maps `chatgpt` / `gemini` to their blocks.
