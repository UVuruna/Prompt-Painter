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

| File | Tier | One line |
|------|------|----------|
| `__init__.py` | Standard | full public-API re-export index, the real interface — [about](__about/__init__.md) |
| `formatters.py` | Standard | human-readable duration/size/percent formatters — [about](__about/formatters.md) |
| `paths.py` | Algorithmic | project paths, CDP/Chrome launch, output layout, `dest_for`/`versioned_dest_for` — [about](__about/paths.md) · [flow](__flow/paths.md) |
| `sheet.py` | Algorithmic | sheet contract rule + file/folder enumerators — [about](__about/sheet.md) · [flow](__flow/sheet.md) |
| `postprocess.py` | Algorithmic | BG removal + crop thresholds, background mode, safety guards — [about](__about/postprocess.md) · [flow](__flow/postprocess.md) |
| `upscale.py` | Algorithmic | Real-ESRGAN binary location, model, gating thresholds — [about](__about/upscale.md) · [flow](__flow/upscale.md) |
| `aspect.py` | Algorithmic | Change Aspect Ratio tool config + shared filter framework — [about](__about/aspect.md) · [flow](__flow/aspect.md) |
| `theme.py` | Algorithmic | GUI palettes, button fills, Day/Night switch art — [about](__about/theme.md) · [flow](__flow/theme.md) |
| `jobs.py` | Algorithmic | dashboard panels, status badges, Main Menu tiles — [about](__about/jobs.md) · [flow](__flow/jobs.md) |
| `jobtemp.py` | Algorithmic | tool temp/restore/before-after tunables — [about](__about/jobtemp.md) · [flow](__flow/jobtemp.md) |
| `ai.py` | Algorithmic | prompt rules + every free-Gemini-API feature's constants — [about](__about/ai.md) · [flow](__flow/ai.md) |
| `sites.py` | Algorithmic | timing + per-site DOM selectors — [about](__about/sites.md) · [flow](__flow/sites.md) |

## Connections

### Uses
- Nothing (constants only, aside from the intra-package leaf imports
  noted above).

### Used by
- [Sheet Parser](../__about/sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- [CDP Driver](../__about/driver.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- [Run Loop](../__about/runner.md) — `Timing`, `STATE_DIRNAME`,
  `REPORT_SUFFIX`, `RETRY_PREAMBLES`, `dest_for`, `PAUSE_POLL_INTERVAL_S`
- [Chrome Launcher](../__about/chrome.md) — `CDP_PORT`, `CHROME_CANDIDATES`,
  `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`
- [Postprocess](../__about/postprocess.md) — `CROP_MARGIN_PX`, `CROP_INK_ALPHA`,
  `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA`, `CLEAN_EDGE_ENABLE`, the
  `BG_MODE_*`/`BG_COLOR_*` block, and the three SAFETY guards
  `SAFETY_MAX_REMOVE_FRAC` / `_WHITE` / `_COLOR`
- [Background Remover](../__about/bg_remove.md) — the same crop/cleanup
  constants plus `BLACK_VOID_MAX`, the `BG_MODE_*`/`BG_COLOR_*` block
  and the three SAFETY guards, imported package-or-standalone
- [Upscale](../__about/upscale.md) — the `UPSCALE_*` block
- [Job Temp](../__about/jobtemp.md) — `PROJECT_ROOT`, `JOBTEMP_DIRNAME`,
  `JOBTEMP_REMOVED_ALPHA`, `JOB_METRIC`, `JOBTEMP_STEPS_SUBDIR`,
  `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`,
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`; [GUI (folder)](../../gui/___gui.md)
  also reads `JOBTEMP_CAP_BANNER_TEXT`
- [Settings](../__about/settings.md) — `SETTINGS_PATH`
- [Main (Entry Point)](../../__about/main.md) /
  [GUI (folder)](../../gui/___gui.md) —
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
- [Change Aspect Ratio](../__about/aspect.md) — `ASPECT_TOL`,
  `ASPECT_FILTER_OFF`, `ASPECT_FILTER_IF`, `ASPECT_FILTER_IF_NOT`,
  `ASPECT_LABEL_DECIMALS`
- [Shared Filter Framework](../__about/filters.md) — `FILTER_KIND_ASPECT_EXACT`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_KIND_ANY_SIDE`,
  `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`, `FILTER_POLARITY_IF`,
  `FILTER_POLARITY_IF_NOT`
- [AI (subfolder)](../ai/___ai.md) — the `GEMINI_*` / `AI_*` block,
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
