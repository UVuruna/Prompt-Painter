# config/

The single home of every tunable value (root Rule #4): connection
and Chrome launch, output layout, sheet-contract constants, the
background tool, timing, and the per-site DOM config blocks.
Selectors rot with every reskin — each DOM hook is a tuple of
fallbacks tried in order, and the driver fails loudly when none
match.

Split by domain into eleven submodules (was one 1,419-line
`config.py` file, root Rule #20 god-file split). `__init__.py`
re-exports the FULL public API of every submodule (`from .paths
import (...)`, one explicit block per submodule — see "Design
Decisions" below), so every existing `config.X` / `from
painter.config import X` call site in the codebase kept working
UNCHANGED across the split.

## Files

### `paths.py` — Paths, CDP, Output Layout
`PROJECT_ROOT`; the CDP/Chrome launch block (`CDP_PORT`, `CDP_URL`,
`CHROME_CANDIDATES`, `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`);
the output layout (`DEFAULT_OUT_DIR`, `STATE_DIRNAME`,
`REPORT_SUFFIX`, `dest_for(drop, site)` — the out/ tree MIRRORS
DOMY's assets/: sheets carry site-agnostic `assets/<category>/<rest>`
paths and `dest_for` injects the site after the category); and
`SETTINGS_PATH` (the GUI's `settings.json`, gitignored). A leaf module
— every other submodule that needs a project-relative path imports
`PROJECT_ROOT` from here.

### `formatters.py` — Human Formatters
`fmt_duration`, `fmt_op_duration` (sub-second precision below 10s —
the fast in-place tools would otherwise flatten to '0s'), `fmt_size`,
`fmt_pct` (magnitude-scaled precision: 2 decimals below 10, 1 decimal
at 10+, so a 3px crop reads '0.24' not a rounded-away '0'). Shared by
the runner report and the GUI dashboard. A leaf module.

### `sheet.py` — Sheet Contract + File Enumerators
`IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN` (the sheet contract's
file-name rule and the REUSE/SUPERSEDED/DO-NOT-GENERATE marker
regex); `selection_base_and_rels(paths)` (the Aspect tool's
multi-file picker plumbing — the common-ancestor base + POSIX rels
for a selection spanning sub-folders); `TOOL_IMAGE_EXTENSIONS`,
`iter_images(folder)` (the shared recursive image enumerator behind
BG/Crop/Upscale/Aspect), `iter_md_files(folder)` (mirrors
`iter_images`, backs the Collections queue's "Add folder…"). A leaf
module.

### `postprocess.py` — Background Removal + Crop Thresholds
`CROP_MARGIN_PX`, the INK-BASED content-box thresholds
(`CROP_INK_ALPHA`, `CROP_MIN_INK_PX`), the border-connected edge-halo
cleanup (`CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`), and the
black-void removal + PER-PATH safety guards (`BLACK_VOID_MAX`,
`SAFETY_MAX_REMOVE_FRAC`, `SAFETY_MAX_REMOVE_FRAC_WHITE` — BLACK
guards at 0.40 since legit bright-on-black clears ~0.24 vs. destroyed
dark rondels at 0.45+; WHITE guards at 0.85 since legit white
backgrounds routinely clear 0.33-0.57). A leaf module (pure numbers).

### `upscale.py` — Real-ESRGAN Upscaler Config
Where the downloaded `realesrgan-ncnn-vulkan` binary lives
(`TOOLS_DIR`, `UPSCALE_DIR`, gitignored), the official release zip
(`UPSCALE_ZIP_URL`), `UPSCALE_MODEL` (`realesrgan-x4plus-anime` since
2026-07-21 research — art-tuned for this project's flat-colour
rondels/badges), and the four editable gate defaults at the ENGINE
level (`UPSCALE_MIN_WIDTH`/`_HEIGHT`, `UPSCALE_ASPECT_MIN`/`_MAX`) plus
the GUI's single min-side spinner seed (`UPSCALE_MIN_SIDE_DEFAULT`,
`UPSCALE_MINDIM_STEP`). Depends on `paths.PROJECT_ROOT`.

### `aspect.py` — Change Aspect Ratio + Shared Filter Framework
The batch deform tool's own constants (`ASPECT_TOL`,
`ASPECT_DEFAULT_W`/`_H`, `ASPECT_LABEL_DECIMALS`) and its optional
scalar input filter (`ASPECT_FILTER_OFF`/`_IF`/`_IF_NOT`,
`ASPECT_FILTER_MODES`, `ASPECT_FILTER_DEFAULT_FROM`/`_TO`) — plus the
newer shared stackable filter framework (owner decision 2026-07-21,
GUI rework Phase 3/4) meant to eventually replace it: the five
`FILTER_KIND_*` identifiers + `FILTER_KINDS`, the two
`FILTER_POLARITY_*` values, `FILTER_PRESETS_SETTING` (the
`settings.json` preset-library key) and `FILTER_ASPECT_EXACT_TOL`
(widens a pinned "Aspect (exact)" condition into a real band, since a
decoded image's W/H almost never lands on an exact float). A leaf
module.

### `theme.py` — GUI Themes + Day/Night Switch
`THEMES` (the two coordinated palettes, night = darkly verbatim, day
= the custom `painter_day` light theme) + `theme_pair`/`status_pair`;
the per-kind SOLID button fills (`BUTTON_FILL`/`BUTTON_TEXT` +
`button_fill_pair`/`button_text_pair` — day's neutral `secondary` is a
LIGHT sand fill, never the dark warm-grey that read brown on the
cream window); the Day/Night switch's full image-based art block
(`SWITCH_*` — geometry, the theme cross-fade timing, the moon's
craters/terminator/mottling, the sun's glow); the SAME
`smooth_transition` cover timing for the OTHER discrete Tk-level
relayouts it still covers — the Controls collapse, a Settings gear, an
Advanced section (`TRANSITION_FADE_MS`/`_STEPS`; NOT a window maximize/
restore any more — owner 2026-07-21 perf fix, see `gui/app_build.md`);
and the window-resize/ScrollFrame debounce constant `RESIZE_SETTLE_MS`
— grouped here as the GUI's broader "visual mechanics" tuning, since it
fits no other domain module. (`SCROLL_FILL_HEIGHT_POLL_MS`, the
ScrollFrame fill_height self-heal poll interval, was REMOVED in the
same perf fix — the re-fit is now fully event-driven, see
[ScrollFrame](../../gui/scroll.md).) Pure hex/number data — no
tkinter/PIL import — so the engine and tests stay framework-free. A
leaf module.

### `jobs.py` — Dashboard Panels, Status Badges, Main Menu
The per-JOB dashboard panel config (`JOB_ORDER`, `JOB_TOOL_KINDS`,
`JOB_LABEL`, `JOB_LOGO`, `JOB_COLORS`, `JOB_METRIC`,
`job_color_pair`, `GRID_COLS_BY_COUNT`); the dashboard status badges
(`BADGES`, `BADGE_ACTION_STEPS`, `BADGE_DONE_STATUS`, the `BADGE_DOT_*`
geometry, `badge_keys_for`); and the Main Menu landing screen (GUI
rework Phase 10: the `MenuTile` frozen dataclass, `MENU_TILES`, the
`MENU_TILE_*` geometry, `TILE_JOB_KINDS` + `tile_for_kind` — the
IconBar's live-status map and its reverse). All PURE data
(strings/numbers/a frozen dataclass tuple), so tests import it with
no tkinter. A leaf module.

### `jobtemp.py` — Tool Temp / Restore / Before-After
The four in-place tools' backup store (`JOBTEMP_DIRNAME`,
`JOBTEMP_REMOVED_ALPHA`); the per-step backup layout (GUI rework
Phase 7/8: `JOBTEMP_STEPS_SUBDIR`, `JOBTEMP_STEP_NAMES` — the
ordering contract `JobTemp.steps_for` relies on, `JOBTEMP_MAX_BYTES`,
`JOBTEMP_KEEP_ALL_STEPS_DEFAULT`, `JOBTEMP_CAP_BANNER_TEXT`); the
per-step restore viewer's filmstrip labels (`JOBTEMP_STEP_LABEL`,
`STEP_RESTORE_CURRENT_LABEL`); and the before/after viewer's
transparency-backdrop checkerboard (`CHECKER_TILE_PX`,
`CHECKER_LIGHT`, `CHECKER_DARK`). Depends on `jobs.JOB_LABEL` (the
four real pipeline stages reuse it rather than duplicating a label).

### `ai.py` — Prompt Rules + AI Features
The per-site prompt suffix machinery (`BACKGROUND_CHOICES`,
`SITE_PROMPT_RULES`, `ASPECT_RULES`/`ASPECT_DEFAULT`/`prompt_suffix`
— the aspect-ratio law picked from the prompt text itself, Gemini's
extra "no reflections" law); the per-agent STYLE clause (`STYLES`,
`STYLE_CHOICES`, `STYLE_DEFAULT`); `SAFER_PREAMBLE` (the safety-refusal
one-shot retry preamble), `CONTINUE_NUDGE` (the ChatGPT stall
nudge), and `IMAGE_RETRY_NUDGE`/`IMAGE_FAILED_RETRY_MAX` (BUG 3,
owner 2026-07-21 — the "retry" word ChatGPT's own "Image generation
failed" answer asks for, and how many times the runner resends it
before giving up on the item); the free Gemini API block (`GEMINI_*` model names,
`AI_CALL_PAUSE_S`/`AI_TIMEOUT_S`/`AI_TEST_PROMPT`, the transient-retry
knobs, `AI_IMAGE_QUOTA_MARKERS`); the AI sheet generator's prompt
templates (`AI_MAX_QUESTIONS`, `SHEETS_DIR`, `AI_QUESTIONS_SYSTEM`,
`AI_SHEET_SYSTEM`, `AI_SHEET_REQUEST`, `AI_REPAIR_PROMPT`); the image
checker's copy (`AI_FLAGS_FILENAME`, `AI_CHECK_INSTRUCTIONS`,
`AI_FIX_NOTE`); the Fixer AI's templates (`AI_FIX_PROMPT_*`,
`FIXER_MODE_*`); and the quota-reset time parser (`QUOTA_RESET_PATTERNS`,
`parse_quota_reset`). Depends on `paths.PROJECT_ROOT` (`SHEETS_DIR`).

### `sites.py` — Timing + Per-Site DOM Selectors
`Timing` (the frozen dataclass of every wait/pace, `TIMING` the
instance), `PAUSE_POLL_INTERVAL_S`, `MIN_IMAGE_PX`; `SiteConfig` (the
per-site DOM hook dataclass — prompt box, send/busy/response/result
selectors, refusal/quota text markers, `image_failed_text_markers`
(BUG 3, owner 2026-07-21 — ChatGPT's own "Image generation failed"
answer text, empty for sites with no such marker), the WEBSITE FIX
attach selectors) and `SITES` (`chatgpt`/`gemini`, both shipping with
WEBSITE FIX disabled until the owner captures real selectors);
`NEW_CHAT_CHOICES`.

## Connections

### Uses
- Nothing (constants only, aside from the intra-package leaf imports
  noted above).

### Used by
- [Sheet Parser](../sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- [CDP Driver](../driver.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- [Run Loop](../runner.md) — `Timing`, `STATE_DIRNAME`,
  `REPORT_SUFFIX`, `SAFER_PREAMBLE`, `dest_for`, `PAUSE_POLL_INTERVAL_S`
- [Chrome Launcher](../chrome.md) — `CDP_PORT`, `CHROME_CANDIDATES`,
  `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`
- [Postprocess](../postprocess.md) — `CROP_MARGIN_PX`, `CROP_INK_ALPHA`,
  `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`,
  `SAFETY_MAX_REMOVE_FRAC`, `SAFETY_MAX_REMOVE_FRAC_WHITE`
- [Background Remover](../bg_remove.md) — the same crop/cleanup
  constants plus `BLACK_VOID_MAX` and the two SAFETY guards,
  imported package-or-standalone
- [Upscale](../upscale.md) — the `UPSCALE_*` block
- [Job Temp](../jobtemp.md) — `PROJECT_ROOT`, `JOBTEMP_DIRNAME`,
  `JOBTEMP_REMOVED_ALPHA`, `JOB_METRIC`, `JOBTEMP_STEPS_SUBDIR`,
  `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`,
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`; [GUI](../../gui.md) also reads
  `JOBTEMP_CAP_BANNER_TEXT`
- [Settings](../settings.md) — `SETTINGS_PATH`
- [Main (Entry Point)](../../main.md) / [GUI](../../gui.md) —
  `CDP_URL`, `DEFAULT_OUT_DIR`, `SITES`, `TIMING`,
  `BACKGROUND_CHOICES`, `prompt_suffix`, `STYLES`/`STYLE_CHOICES`/
  `STYLE_DEFAULT`, `RESIZE_SETTLE_MS`, the `ASPECT_FILTER_*`
  constants, `iter_images`, `iter_md_files`, the
  `SWITCH_*`/`TRANSITION_FADE_*` theming-and-cover art block, the
  `BADGES` block + `badge_keys_for`, the `FILTER_KIND_*`/
  `FILTER_KINDS`/`FILTER_POLARITY_*`/`FILTER_PRESETS_SETTING`/
  `FILTER_ASPECT_EXACT_TOL` block, `MenuTile`/`MENU_TILES`/
  `MENU_TILE_*`, `TILE_JOB_KINDS`, `tile_for_kind`, `GEMINI_IMAGE_MODEL`,
  `AI_IMAGE_GATE_MESSAGE`, `AI_IMAGE_PROBE_PROMPT`, and
  `FIXER_MODE_API`/`FIXER_MODE_WEBSITE`/`FIXER_MODE_CHOICES`
- [Change Aspect Ratio](../aspect.md) — `ASPECT_TOL`,
  `ASPECT_FILTER_OFF`, `ASPECT_FILTER_IF`, `ASPECT_FILTER_IF_NOT`,
  `ASPECT_LABEL_DECIMALS`
- [Shared Filter Framework](../filters.md) — `FILTER_KIND_ASPECT_EXACT`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_KIND_ANY_SIDE`,
  `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`, `FILTER_POLARITY_IF`,
  `FILTER_POLARITY_IF_NOT`
- [AI Client & Flows](../ai.md) — the `GEMINI_*` / `AI_*` block,
  `SITES` (the re-send reverse map), `STATE_DIRNAME`, `PROJECT_ROOT`

## Design Decisions

- **God-file split by domain, not mechanically.** The former
  1,419-line `config.py` (root Rule #20) is now eleven submodules,
  each a cohesive tunable domain, with `paths.py`/`formatters.py`
  as dependency-free leaves and every cross-reference (`upscale.py`
  and `ai.py` need `paths.PROJECT_ROOT`; `jobtemp.py` needs
  `jobs.JOB_LABEL`) an explicit intra-package import — no circular
  imports.
- **`__init__.py` re-exports the FULL public API as the real
  interface, not a compatibility shim** (owner-approved 2026-07-21):
  every one of the 196 public names the old `config.py` defined is
  imported explicitly into `__init__.py` and listed in `__all__`, so
  `painter.config.SITES`, `from painter.config import dest_for`, and
  every other pre-split call site anywhere in the codebase kept
  working UNCHANGED — root Rule #6 ("no backward-compatibility
  wrappers") does not apply here, since this re-export IS the
  package's public interface, not a bridge to a deleted old API.
  Verified: a name-diff between the old `config.py`'s module-level
  definitions and the new package's `dir()` shows zero missing and
  zero extra.
- **Zero call-site changes anywhere.** `gui.py`, `main.py`, every
  `painter/*.py` engine module and every test already used
  `from painter.config import X` (never `import painter.config as
  config` + attribute access in actual code — only in comments), so
  the split needed no caller edits at all; the full test suite (613
  passed, 1 skipped) stayed green through the split with no test
  changes.
