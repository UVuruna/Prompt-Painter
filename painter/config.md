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
- [Run Loop](runner.md) — `Timing`, `STATE_DIRNAME`,
  `REPORT_SUFFIX`, `SAFER_PREAMBLE`, `dest_for`, `PAUSE_POLL_INTERVAL_S`
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
- [Job Temp](jobtemp.md) — `PROJECT_ROOT`, `JOBTEMP_DIRNAME`,
  `JOBTEMP_REMOVED_ALPHA`, `JOB_METRIC`, and (GUI rework Phase 7)
  `JOBTEMP_STEPS_SUBDIR`, `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`,
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`; [GUI](../gui.md) also reads
  `JOBTEMP_CAP_BANNER_TEXT` (GUI rework Phase 8's over-cap dashboard
  banner copy)
- [Settings](settings.md) — `SETTINGS_PATH`
- [Main (Entry Point)](../main.md) / [GUI](../gui.md) — `CDP_URL`,
  `DEFAULT_OUT_DIR`, `SITES`, `TIMING`, `BACKGROUND_CHOICES`,
  `prompt_suffix`; GUI also `STYLES`/`STYLE_CHOICES`/`STYLE_DEFAULT`,
  `RESIZE_SETTLE_MS`, the `ASPECT_FILTER_*` constants, `iter_images`,
  `iter_md_files`,
  the `SWITCH_*`/`TRANSITION_FADE_*` theming-and-cover art block, the
  `BADGES` block + `badge_keys_for` (the dashboard status badges),
  (GUI rework Phase 4) the `FILTER_KIND_*`/`FILTER_KINDS`/
  `FILTER_POLARITY_*`/`FILTER_PRESETS_SETTING`/`FILTER_ASPECT_EXACT_TOL`
  block behind `FilterEditor` and the standalone Aspect tool's own
  panel it migrated (GUI rework Phase 4's `AspectRatioDialog`, later
  retired — GUI rework Phase 14 — by `AspectSettingsPanel`), and
  (GUI rework Phase 10) `MenuTile`/`MENU_TILES`/`MENU_TILE_*` behind
  `MainMenu`, (GUI rework Phase 11) `TILE_JOB_KINDS` behind the
  running view's `IconBar`, (GUI rework Phase 15) `tile_for_kind`
  behind `PainterGui._tool_panel_key`, and (GUI rework Phase 19)
  `GEMINI_IMAGE_MODEL`, `AI_IMAGE_GATE_MESSAGE`, `AI_IMAGE_PROBE_PROMPT`
  behind `ApiImageAdapter`/`ApiImageGenPanel`
- [Change Aspect Ratio](aspect.md) — `ASPECT_TOL`, `ASPECT_FILTER_OFF`,
  `ASPECT_FILTER_IF`, `ASPECT_FILTER_IF_NOT`, `ASPECT_LABEL_DECIMALS`
- [Shared Filter Framework](filters.md) — `FILTER_KIND_ASPECT_EXACT`,
  `FILTER_KIND_ASPECT_RANGE`, `FILTER_KIND_ANY_SIDE`,
  `FILTER_KIND_WIDTH`, `FILTER_KIND_HEIGHT`, `FILTER_POLARITY_IF`,
  `FILTER_POLARITY_IF_NOT`
- [AI Client & Flows](ai.md) — the `GEMINI_*` / `AI_*` block,
  `SITES` (the re-send reverse map), `STATE_DIRNAME`, `PROJECT_ROOT`

## Values

- `CDP_PORT` / `CDP_URL` — Chrome's debug endpoint.
- `CHROME_CANDIDATES` — where chrome.exe usually lives.
- `CHROME_PROFILE_DIR` — the dedicated automation profile
  (`chrome-profile/`, gitignored; Chrome 136+ refuses CDP on the
  default profile). Log in once there; sessions persist.
- `DEFAULT_OUT_DIR`, `STATE_DIRNAME`,
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
  final box. CHANGED vs SKIPPED is now keyed on EXACT resolution (owner
  2026-07-19, reversing the old `CROP_MIN_TRIM_PX` slop): `crop_transparent`
  counts a crop as soon as the cropped output differs from the input by
  ≥ 1px on ANY side — a 1254×1254 → 1254×1251 3px trim IS a crop even
  though its % rounds tiny — and returns "nothing" ONLY when the box +
  margin lands on the full frame (0px change, no rewrite, no temp
  backup). There is no negligible-trim threshold any more.
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
  `UPSCALE_ZIP_URL`, `UPSCALE_MODEL`, `UPSCALE_MIN_WIDTH`,
  `UPSCALE_MIN_HEIGHT`, `UPSCALE_ASPECT_MIN`, `UPSCALE_ASPECT_MAX`,
  `UPSCALE_MINDIM_STEP` — the Real-ESRGAN upscaler: where the
  downloaded binary lives (`tools/`, gitignored), the official
  release zip, `UPSCALE_MODEL` (the ncnn net passed as `-n`;
  `realesrgan-x4plus-anime` since 2026-07-21 research — art-tuned for
  this project's flat-colour rondels/badges, A/B-verified visibly
  crisper than the general-purpose `realesrgan-x4plus` with no colour
  shift or banding regression, see [Upscale](upscale.md)), and the
  FOUR editable gate DEFAULTS at the ENGINE level (owner 2026-07-19,
  reproducing the old locked `min_px=800`/`aspect_tol=0.1` rule) —
  `upscale_if_small`'s own signature/defaults, UNCHANGED by the GUI
  rework — an image qualifies when its aspect W/H is within
  `[UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX]` (0.9–1.1) AND
  `W < UPSCALE_MIN_WIDTH` OR `H < UPSCALE_MIN_HEIGHT` (800 / 800).
  GUI rework Phase 6 simplified the GUI's OWN exposure of this gate
  from four fields (PER AGENT and in the standalone Upscale dialog) to
  ONE min-side Spinner (`UPSCALE_MINDIM_STEP` still drives it) plus an
  embedded [Shared Filter Framework](filters.md) `FilterEditor` — see
  `UPSCALE_MIN_SIDE_DEFAULT` next and [GUI](../gui.md)'s upscale-gate
  section; `gui._upscale_params_from_side_and_filter` is the pure
  resolution function, `gui._migrate_legacy_upscale_gate` the one-time
  settings migration off these OLD four fields. The old `*_STEP` /
  `*_DECIMALS` pair that drove the removed aspect-FROM/aspect-TO
  spinner fields (`UPSCALE_ASPECT_STEP`, `UPSCALE_ASPECT_DECIMALS`) is
  GONE — nothing renders those two fields any more (the aspect band is
  now authored through the FilterEditor's own generic row formatting).
- `UPSCALE_MIN_SIDE_DEFAULT` — GUI rework Phase 6: the seed default for
  the upscale gate's single min-side Spinner (both per-agent and the
  standalone dialog) — reuses `UPSCALE_MIN_WIDTH`'s value (`==
  UPSCALE_MIN_HEIGHT` already, by design), so the shipped default
  behaves byte-identically to the old four-field gate's own default.
- `ASPECT_TOL`, `ASPECT_DEFAULT_W`, `ASPECT_DEFAULT_H` — the
  [Change Aspect Ratio](aspect.md) batch deform tool: `ASPECT_TOL`
  (0.001) is how close an image's W/H must be to the target ratio to
  count as already-at-ratio (left byte-unchanged, no write);
  `ASPECT_DEFAULT_W`/`ASPECT_DEFAULT_H` (16 / 9) preselect the GUI's
  ratio prompt. `selection_base_and_rels(paths)` (owner 2026-07-19)
  backs the tool's MULTI-FILE picker — Aspect ratio picks INDIVIDUAL
  image files (a folder can hold mixed ratios), and this returns the
  `(base, [rel, ...])` pair the job machinery keys on (base = the
  common-ancestor DIRECTORY of the picks, one folder ⇒ base = that
  folder, rel = filename), so a selection spanning sub-folders still
  groups + restores correctly.
- `ASPECT_LABEL_DECIMALS` (3) — GUI rework Phase 5 (owner decision
  2026-07-21): the visual aspect-ratio editor's live dual label shows
  the target ratio as an exact DECIMAL, standard-ROUNDED to this many
  places (16:9 -> "1.778:1") — the default `decimals` argument of
  [Change Aspect Ratio](aspect.md)'s pure `decimal_ratio_label`, kept
  here (not in gui.py) so it stays importable with no tkinter
  dependency, same as every other engine-side constant on this page.
- `ASPECT_FILTER_OFF` / `ASPECT_FILTER_IF` / `ASPECT_FILTER_IF_NOT`,
  `ASPECT_FILTER_MODES`, `ASPECT_FILTER_DEFAULT_FROM` /
  `ASPECT_FILTER_DEFAULT_TO` — the Aspect tool's optional INPUT FILTER
  on each image's CURRENT ratio W/H (owner 2026-07-19). A single
  `[from, to]` range plus a MODE: `off` processes all, `IF` processes
  ONLY images whose W/H is in range, `IF NOT` skips those and processes
  the rest ([Change Aspect Ratio](aspect.md) applies it; a filtered-out
  image is a plain "nothing" skip). The mode strings double as the
  dialog combobox labels; the defaults pre-fill the ~square band
  (0.9–1.1). Since 0.0.078 the Aspect tool accepts FILES **or** a whole
  FOLDER (the filter makes folders useful — skip the already-good ones).
- `FILTER_KIND_ASPECT_EXACT` / `FILTER_KIND_ASPECT_RANGE` /
  `FILTER_KIND_ANY_SIDE` / `FILTER_KIND_WIDTH` / `FILTER_KIND_HEIGHT`,
  `FILTER_KINDS`, `FILTER_POLARITY_IF` / `FILTER_POLARITY_IF_NOT`,
  `FILTER_PRESETS_SETTING` — GUI rework Phase 3 (owner decision
  2026-07-21): the identifier strings behind the new stackable
  [Shared Filter Framework](filters.md), meant to eventually replace
  the `ASPECT_FILTER_*` scalar above and Upscale's bespoke gate with
  ONE reusable `FilterCondition` shape — DONE for Upscale as of Phase
  6 (its old four-field min-W/min-H/aspect-FROM/aspect-TO gate is now
  ONE min-side number + an embedded `FilterEditor`; `ASPECT_FILTER_*`
  itself is still read once by the Phase 4 migration but no longer
  written). Five kinds — the aspect ratio
  W/H (`ASPECT_EXACT` pins `lo == hi` to one point, `ASPECT_RANGE` is a
  typed band, identical comparison either way), `ANY_SIDE` (both W and
  H at once, orientation-agnostic: `lo <= min(w,h)` AND
  `max(w,h) <= hi`), and the raw `WIDTH`/`HEIGHT` in pixels
  (orientation matters). `FILTER_KINDS` is the ordered tuple the
  future `FilterEditor`'s kind combobox will list — the values ARE the
  display text (Rule #4, same convention as `ASPECT_FILTER_MODES` /
  `STYLE_CHOICES`). `FILTER_POLARITY_IF` / `FILTER_POLARITY_IF_NOT`
  reuse the legacy `ASPECT_FILTER_IF` / `ASPECT_FILTER_IF_NOT` spelling
  exactly, so a future settings migration needs no translation table.
  `FILTER_PRESETS_SETTING` (`"filter_presets"`) is the `settings.json`
  key the shared preset LIBRARY lives under — one flat
  `{name: [condition-dict, ...]}` dict every `FilterEditor` instance
  reads/writes (GUI rework Phase 4 wired this in: `gui.FilterEditor` +
  `AspectRatioDialog`, its first caller, since retired — GUI rework
  Phase 14 — by `AspectSettingsPanel`, one of several current callers
  — see [GUI](../gui.md)).
- `FILTER_ASPECT_EXACT_TOL` (`0.02`) — GUI rework Phase 4, fixes Phase
  3's flagged caveat: a pinned "Aspect (exact)" condition is a
  razor-thin `lo == hi` float-equality test (correct for the engine —
  see [Shared Filter Framework](filters.md)'s "no hidden epsilon"
  design decision) but useless authored raw, since a REAL decoded
  image's width/height division almost never lands on that exact
  double (a "square" export at 1000x1001 divides to 0.999000999...,
  not 1.0). `FilterEditor` authors this kind from a SINGLE typed ratio
  and widens it into `[ratio - tol, ratio + tol]` before building the
  `FilterCondition`, so ordinary near-square exports still match;
  `matches()` itself is unchanged by this constant — it only affects
  what the widget WRITES into a condition's `lo`/`hi` for this one
  kind. The widget's OWN pixel-geometry constants (row field widths,
  decimals, preset combo width) live in `gui.py`'s own Rule #4 block
  instead, alongside every other dialog's `*_ENTRY_W`/`*_PAD_PX` —
  this file only holds the one engine-relevant tolerance.
- `TOOL_IMAGE_EXTENSIONS`, `iter_images(folder)` — the shared image
  enumerator (owner 2026-07-19): every image file (`.png/.jpg/.jpeg/
  .webp`) under a folder, sorted, recursive. ONE home for the
  folder-based tools (BG / Crop / Upscale) and the Aspect tool's folder
  input (`gui._iter_images` delegates here — Rule #5).
- `iter_md_files(folder)` — the Collections queue's folder-input
  enumerator (GUI rework Phase 2, 2026-07-21): every `.md` file under a
  folder, sorted, recursive — mirrors `iter_images` byte-for-byte
  (same local-import/`sorted(rglob(...))` shape), just filtering on the
  `.md` suffix directly instead of `TOOL_IMAGE_EXTENSIONS` (a sheet has
  exactly one extension, so no shared tuple constant is needed). Backs
  [GUI](../gui.md)'s "Add folder…" button beside Add…/Remove/Clear —
  point it at a folder of prompt sheets and every sheet underneath,
  however nested, queues in one go.
- `JOB_ORDER`, `JOB_TOOL_KINDS`, `JOB_LABEL`, `JOB_LOGO`,
  `JOB_COLORS`, `JOB_METRIC`, `job_color_pair(kind)`,
  `GRID_COLS_BY_COUNT` — the dashboard per-JOB panels (owner
  2026-07-19). The dashboard shows one panel PER RUNNING JOB — the two
  gen SITES, the API IMAGE GEN job (GUI rework Phase 19 — same
  "generation" tier, driven through the paid REST API instead of a
  browser tab; see [GUI](../gui.md)'s `ApiImageAdapter`/
  `ApiImageGenPanel`) plus the four in-place TOOLS plus the AI CHECKER
  (owner 2026-07-20), up to eight in parallel.
  `JOB_ORDER` is the fixed priority (gen first) that row-major places
  panels so ChatGPT + Gemini + API Image GEN always take the top row;
  `GRID_COLS_BY_COUNT` (1→1, 2→2, 3→3, 4→2, 5→2, 6→2, 7→3, 8→3, rows =
  ceil(N/cols)) is the responsive shape (8 added Phase 19, same 3-column
  shape 7 already had — one more empty cell). Each job carries a
  `JOB_LABEL` (the three tool buttons drop "only"), an ICON stem in
  `JOB_LOGO` — the two sites their brand logo, `"api_image"` REUSING the
  Gemini logo (it IS Gemini, just via the REST API — the same icon
  `MENU_TILES`'s own `api_image_gen` tile already picked), the four
  tools dedicated PNG icons (`bg`/`crop`/`upscale`/`aspect`, replacing
  the old `JOB_EMOJI` marks; `gui.icon()` resolves each stem to svg or
  png), the checker the `ai` png. Plus a `(day, night)` `JOB_COLORS`
  pair (`job_color_pair` returns it, auto-flipping on
  `set_appearance_mode`) — `"api_image"`'s own orange pair is the SAME
  tuple `MENU_TILES`'s `api_image_gen` tile reads back (one hue, not two
  literals that could drift, see `MENU_TILES` below) — and a `JOB_METRIC`
  word (removed / reduction / increase / deformation; the checker's odd
  one out is `defects` — a COUNT, not a %) the panel shows — `"api_image"`
  has NO entry here, same as chatgpt/gemini (`DashPanel`, not `ToolPanel`,
  shows no per-image metric column). Pure strings/numbers, so the tests
  import it without tkinter.
- `JOBTEMP_DIRNAME`, `JOBTEMP_REMOVED_ALPHA` — the tool temp/restore
  store (owner 2026-07-19). `JOBTEMP_DIRNAME` (`.painter_tmp`,
  gitignored) is the PROJECT_ROOT-relative backup root
  [Job Temp](jobtemp.md) uses; `JOBTEMP_REMOVED_ALPHA` (40) is the
  alpha below which a pixel counts as "removed" for the BG metric (the
  same opacity notion as `CROP_INK_ALPHA` / `CLEAN_EDGE_ALPHA`).
- `JOBTEMP_STEPS_SUBDIR`, `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`,
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT` — GUI rework Phase 7 (owner decision
  2026-07-21): the on-disk shape for per-step backups; Phase 8 wired
  them up for real over the site-generation pipeline (BG → Crop →
  Aspect(force) → Upscale) on top of
  [Job Temp](jobtemp.md)'s existing single-backup store.
  `JOBTEMP_STEPS_SUBDIR` (`"__steps__"`) is the reserved subdir name a
  NAMED step's backup is namespaced under, so it can never collide with
  the plain `step=None` path the four standalone tools have always used
  (see Job Temp's "On-disk layout" for the full byte-for-byte
  guarantee). `JOBTEMP_STEP_NAMES` (`"original", "bg", "crop", "aspect",
  "upscale", "fixer"`) is the ORDERING CONTRACT `JobTemp.steps_for(rel)`
  relies on: the pipeline's own BG→Crop→Aspect→Upscale order, bookended
  by `"original"` (the pristine baseline, before the pipeline touches
  the file — what a "restore everything to pristine" restores to, via
  the explicit `restore_to(rel, step="original")`) and `"fixer"` (the
  Fixer AI's pre-fix snapshot, Phase 20, taken after the pipeline and
  checker have already run). Phase 8's `gui._run_pipeline_steps` DEDUPS
  the first ENABLED step's own name against `"original"` (byte-identical
  backups of the same instant otherwise), so `steps_for()` in practice
  never lists BOTH — a filmstrip for an image whose first enabled step
  was BG lists `["original", "crop", ...]`, never `["original", "bg",
  "crop", ...]`. `JOBTEMP_MAX_BYTES` (`4 * 1024**3`, 4 GiB)
  is the intermediate-backup disk cap `JobTemp.over_cap()` compares
  cumulative backup bytes against — a SIGNAL only, `JobTemp` never
  auto-evicts; the Findings memory math (4 steps × ~3MB/image ⇒
  ~300 images overnight peaking ~3.6–4.5GB) is why 4 GiB was chosen.
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT` (`True`) is the default for
  `AgentPanel.keep_all_steps_var`, the per-agent "Keep every pipeline
  step (uses more disk)" toggle (Phase 8) — not read by `jobtemp.py`
  itself, which has no notion of "agents"; when off, `gui.
  _run_pipeline_steps` falls back to original-only SILENTLY (never
  `on_cap`, which is reserved for a REAL cap hit).
- `JOBTEMP_CAP_BANNER_TEXT` — GUI rework Phase 8: the LOUD, PERSISTENT
  dashboard banner text a site job's panel shows the ONE time its
  `JobTemp` crosses `JOBTEMP_MAX_BYTES` (owner decision: "loud
  persistent dashboard banner, not just a log line"). Formatted from
  `JOBTEMP_MAX_BYTES` itself at module load, so the GiB figure in the
  message can never drift from the real cap. A plain static string —
  lives here like every other user-facing copy constant
  (`SAFER_PREAMBLE`, `CONTINUE_NUDGE`, `AI_CHECK_INSTRUCTIONS`).
- `JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL` — GUI rework
  Phase 9: the per-step restore viewer's (`gui.StepRestoreWindow`)
  filmstrip labels. `JOBTEMP_STEP_LABEL` maps each raw
  `JOBTEMP_STEP_NAMES` key to what the owner actually sees — the four
  real pipeline stages REUSE `JOB_LABEL` (one label per tool kind,
  never duplicated), `"original"`/`"fixer"` get their own short label
  since neither is a tool. `STEP_RESTORE_CURRENT_LABEL` (`"Current"`)
  is the filmstrip's own final entry — the LIVE file, not a backup, so
  it carries no "Restore to here" of its own. Both are consumed by
  `gui._filmstrip_stages`, the pure list-builder behind the viewer.
- `CHECKER_TILE_PX`, `CHECKER_LIGHT`, `CHECKER_DARK` — the neutral
  light/dark checkerboard the before/after viewer composites a
  transparent AFTER over, so a removed (transparent) background reads as
  removed rather than as the panel colour. Theme-agnostic greys — a
  transparency backdrop, not app chrome.
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
  advice / superseded / code_fg / btn_text / **skip** / **toolchanged**
  — the last TWO are the tool-panel Treeview row tints (owner
  2026-07-19): `skip` a muted grey for SKIPPED (unchanged) rows,
  `toolchanged` a BOLD striking green/teal (`#2ee59d` night / `#0a9d6e`
  day) for CHANGED (restorable) rows so the two never blur together).
  `theme_pair(key)`
  returns the `(day, night)` tuple every customtkinter colour kwarg
  passes so `set_appearance_mode()` flips them; `status_pair` does
  the same for the status block. `BUTTON_FILL` / `BUTTON_TEXT` +
  `button_fill_pair(kind)` / `button_text_pair(kind)` (owner 2026-07-19)
  hold the SOLID button fill + label per kind (secondary / success /
  danger / info) as `(day, night)`, DECOUPLED from the palette keys so
  the DAY shade differs from NIGHT for every kind and the neutral
  `secondary` is a LIGHT sand fill with DARK text on day (never the dark
  warm-grey that read brown on the cream window); coloured kinds keep a
  white label in both themes. The `SWITCH_*` constants are the
  Day/Night switch geometry (scaled from `SWITCH_H`) and its
  IMAGE-BASED art (owner 2026-07-18 — tkinter Canvas has no
  anti-aliasing, so the switch composites PIL images, not raw ovals):
  the two track pills are the owner's website SVGs
  (`SWITCH_TRACK_NIGHT_SVG` / `SWITCH_TRACK_DAY_SVG`, in
  `assets/icons/`), and the moon/sun knobs are PIL radial-gradient
  colours — the MOON a real moon (owner 2026-07-20): silver gradient
  (`SWITCH_MOON_CENTER`/`_EDGE`) + 7 varied craters
  (`SWITCH_CRATERS`, floors `SWITCH_CRATER`) each with a subtle
  alpha-blended lit rim arc (`SWITCH_CRATER_RIM` /
  `_RIM_FRAC` / `_RIM_ALPHA` at 185 — a solid near-white arc read as a
  pac-man ring — / `_RIM_ARC_DEG`), TERMINATOR shading (lit from
  `SWITCH_MOON_LIGHT_DIR`, far limb falling to
  `SWITCH_MOON_DARK_FLOOR` across a `SWITCH_MOON_TERMINATOR_SOFT`
  smoothstep band) and deterministic value-noise mottling
  (`SWITCH_MOON_NOISE_SEED`/`_CELLS`/`_AMPL` — the seed is FIXED so
  the moon is identical every build; 11.0 amplitude, 6.0 measured
  invisible) — the gold sun (`SWITCH_SUN_CENTER`/`_EDGE`) + a blurred
  glow (`SWITCH_SUN_GLOW*`) — rendered at `SWITCH_SUPERSAMPLE`x and
  LANCZOS-downscaled. The snapshot-cover FADE constants live here too:
  `SWITCH_FADE_MS` (≈500 ms) / `SWITCH_FADE_STEPS` (28) time the
  ceremonial THEME cross-fade (lengthened 2026-07-19 to kill the flip
  flash), `TRANSITION_FADE_MS` (260 ms) / `TRANSITION_FADE_STEPS` (14)
  the snappier covers the SAME `gui.smooth_transition` mechanism puts
  behind the Controls collapse, each agent's Settings gear and a
  window maximize/restore (owner 2026-07-20), and
  `SWITCH_COVER_ICON_FRAC` (0.30) / `SWITCH_COVER_ICON_SS`
  size the BIG centred sun/moon that rides the theme cover — the SAME
  renderers as the switch knob, showing the theme being switched TO.
  This block is
  PURE hex/number data — no tkinter/ttkbootstrap/PIL import — so the
  engine and tests stay framework-free; [GUI](../gui.md) rasterizes it
  into the live art.
- `RESIZE_SETTLE_MS` — the smooth-resize debounce window (owner
  2026-07-19, widened in role 2026-07-20). customtkinter re-renders on
  every intermediate `<Configure>`, so a window drag / maximize used to
  run the [GUI](../gui.md) `ScrollFrame`'s expensive re-fit
  (scrollregion bbox + fill-height) per frame. Everything deferrable
  now waits this many ms (150) after the LAST `<Configure>` ("wait for
  mouse release") and runs ONCE: the `ScrollFrame` re-fit AND its
  body-width apply, the Select window's label wraplength re-flow, and
  the main window's buffered dashboard events (the root watcher
  buffers `__event__` messages during an active drag and flushes them
  on this same settle).
- `BADGES`, `BADGE_ACTION_STEPS`, `BADGE_DONE_STATUS`,
  `BADGE_DOT_PX` / `BADGE_DOT_GAP_PX` / `BADGE_DOT_SS`,
  `badge_keys_for(actions, retried)` — the dashboard STATUS BADGES
  (owner 2026-07-20): small coloured dots beside an image row's name
  in the gen panels' Collections tree, marking what actually HAPPENED
  to that image. `BADGES` is pure data — key → (dot colour, legend
  label), render order (`bg`, `crop`, `aspect`, `upscale`, `retry` —
  the pipeline order, retry last); deliberately THEME-AGNOSTIC
  mid-tones so one dot reads on both tree backgrounds, and the owner
  retints/renames here. GUI rework Phase 8 added `"aspect"` (`#d946ef`,
  "aspect forced") for the new Force-Aspect pipeline step — a
  magenta/fuchsia picked from the same Tailwind-500 family the other
  three already use (green-500/amber-500/blue-500), reusing the SAME
  hue `JOB_COLORS["aspect"]` already ties to "aspect" everywhere else
  in the app. `BADGE_ACTION_STEPS` maps the runner's post_save step
  names (`REMOVE BG` / `CROP` / `ASPECT` / `UPSCALE`) to badge keys;
  `badge_keys_for` parses the action string ("REMOVE BG: done, CROP:
  done, ASPECT: done, UPSCALE: nothing") and awards a badge ONLY on
  status `BADGE_DONE_STATUS` ("done" — never nothing/unclear/FAILED;
  unknown segments are ignored, badges only assert a positive), plus
  the `retry` badge when the safer retry produced the image. The `DOT_*`
  numbers drive [GUI](../gui.md)'s PIL dot rasterizer (supersampled +
  LANCZOS) — dots are PIL-drawn, NOT emoji: Tk 8.6 on Windows renders
  colour emoji as identical monochrome circles (verified live
  2026-07-20).
- `MenuTile`, `MENU_TILES`, `MENU_TILE_RADIUS`, `MENU_TILE_COLS`,
  `MENU_TILE_W` / `MENU_TILE_H`, `MENU_TILE_GAP_PX`, `MENU_TILE_ICON_PX`,
  `MENU_TILE_BORDER_PX` / `MENU_TILE_BORDER_HOVER_PX` — the Main Menu
  landing screen (GUI rework Phase 10, owner decision 2026-07-21): a
  frozen `MenuTile` dataclass (`id`, `label`, `description`, `icon`
  stem, `color` `(day, night)` accent pair, `enabled`) and the 8-entry
  `MENU_TILES` tuple behind it — `website_gen`, `ai_sheet_gen`,
  `api_image_gen`, `image_checker`, `bg`, `crop`, `upscale`, `aspect` —
  PURE DATA, same shape/spirit as `SiteConfig`/`SITES` below, so
  `test_menu_tiles_cover_all_eight_functionalities_with_unique_ids`
  asserts coverage/uniqueness with no tkinter import; only
  [GUI](../gui.md)'s `MainMenu` turns an entry into a widget. `api_image_gen`
  was a shown-but-inert placeholder (`enabled=False`) through Phase 18;
  GUI rework Phase 19 flips it to `enabled=True` and wires the real
  handler — EVERY tile is now live, `test_menu_tiles_none_are_disabled`.
  Six tiles reuse `JOB_LABEL`/`JOB_LOGO`/`JOB_COLORS` directly (bg/crop/
  upscale/aspect map straight onto their existing job kind;
  `image_checker` onto `"aicheck"`; `api_image_gen` onto `"api_image"`,
  Phase 19); the other two (website_gen/ai_sheet_gen) have no single
  matching `JOB_COLORS` entry (Website GEN spans BOTH gen sites,
  ai_sheet_gen is a net-new AI feature with no dashboard job at all)
  and carry their own accent tuples (indigo/yellow) picked to stay
  visually distinct from the `JOB_COLORS` hues already in use.
  `MENU_TILE_RADIUS` (16) sits in DESIGN.md's "cards, panels" bracket,
  one notch above `gui.py`'s own smaller `BTN_RADIUS`/`INPUT_RADIUS`
  "buttons, inputs" bracket; the rest are the tile grid's own Rule #4
  geometry (a 4×2 layout for today's 8 tiles, gap/icon-size/border-width
  — `_HOVER_PX` is the ONE thing that changes on a tile's hover, a
  border-width widen with no fill-colour cascade to keep in sync).
- `TILE_JOB_KINDS` — a `{MENU_TILES id: (JOB_ORDER kind, ...)}` dict
  (GUI rework Phase 11) behind [GUI](../gui.md)'s running-view
  `IconBar`: which kind(s) light a tile up while at least one is
  active (`website_gen` → `("chatgpt", "gemini")`, the six tool/
  checker/api-image tiles → their own single matching kind,
  `ai_sheet_gen` → `()` since it has no dashboard job of its own —
  `api_image_gen` used to be a SECOND empty-tuple entry through Phase
  18; GUI rework Phase 19 gives it `("api_image",)`, the same
  single-kind shape bg/crop/upscale/aspect already have). PURE DATA
  again — a new job kind only ever needs a data change here, never an
  `IconBar` code change; `test_tile_job_kinds_*` in `test_config.py`
  checks coverage BOTH ways (every `MENU_TILES` id has an entry, every
  `JOB_ORDER` kind is reachable from some tile).
- `tile_for_kind(kind) -> str | None` (GUI rework Phase 15) — the
  REVERSE of `TILE_JOB_KINDS`: the one `MENU_TILES` id whose kinds
  tuple is EXACTLY `(kind,)`, i.e. a job kind's OWN persistent-panel
  tile (bg/crop/upscale/aspect resolve to themselves — tile id ==
  slot; `"aicheck"` resolves to `"image_checker"`, since the AI
  checker's dashboard slot predates the tile system, GUI rework Phase
  11, and never renamed to match it; `"api_image"` resolves to
  `"api_image_gen"`, GUI rework Phase 19 — SAME asymmetry as the
  checker's, `ApiImageGenPanel`'s own `_tool_panels` key differing
  from its JOB_ORDER slot); `None` for a kind sharing a tile with
  another (chatgpt/gemini under `"website_gen"`) or with no tile at
  all. Behind [GUI](../gui.md)'s `PainterGui._tool_panel_key`, the one
  bridge `_toggle_pause_job`/the `__worker_done__`/`__tool_done__`
  dispatch branches need to reach a job's settings panel from its
  JOB_ORDER kind — PURE DATA-DRIVEN, so a future standalone job kind
  never needs a new branch there, only a `TILE_JOB_KINDS` entry;
  `test_tile_for_kind_*` in `test_config.py`.
- `BACKGROUND_CHOICES`, `SITE_PROMPT_RULES`, `GEMINI_ASPECT_RULES`,
  `prompt_suffix(site_key, background, prompt_text, style=None)` — the
  rule block appended to every prompt: the chosen background (each
  site's dropdown defaults to its `default_background` — ChatGPT
  transparent, Gemini white; `ApiImageGenPanel`'s own default is
  "white" too, chosen directly by the panel rather than a
  `default_background` field — the paid image model has no
  `SiteConfig`, and cannot render real transparency at all, spec item
  3) plus the site's forced laws (owner 2026-07-17). Gemini's aspect
  law is picked FROM THE PROMPT: TALL/lancet prompts get tall
  portrait, everything else (badges, rondels, medallions) a perfect
  1:1 square; plus NO reflections. `SITE_PROMPT_RULES["api_image"]`
  (GUI rework Phase 19) is an EMPTY tuple — no extra rule yet, since
  there is no live drift evidence for the API model the way there is
  for the Gemini WEBSITE's reflections; a required entry regardless
  (`prompt_suffix` indexes `SITE_PROMPT_RULES[site_key]` directly, so
  a missing key would raise) — add a real rule here if the owner
  observes the same drift pattern from the API.
- `STYLES`, `STYLE_CHOICES`, `STYLE_DEFAULT` — the per-agent STYLE
  clause (owner 2026-07-19). `STYLES` maps 7 named keys ("None" +
  Realistic / Oil painting / Watercolor / 3D render / Flat vector / Ink
  engraving) to an appended clause; "None" → `""` (nothing appended).
  Each [GUI](../gui.md) AgentPanel picks one; `prompt_suffix`'s `style`
  arg appends that clause at the very END of the suffix (AFTER the
  background rule + Gemini laws), only when it is not "None".
  `STYLE_CHOICES` is the dropdown order (None first). Pure data — reword
  the clauses here without touching logic.
- `SAFER_PREAMBLE` — the allegory-framing note prepended on a
  one-shot safer retry after a SAFETY refusal (opt-in). An honest
  reframing of legitimate symbolic art (no real people, non-graphic),
  never a way to force disallowed content.
- `CONTINUE_NUDGE` — the short "continue" message the runner sends
  ONCE into the SAME chat when ChatGPT stalls on an image (the driver's
  `NoImage`: done edge fired, empty answer, no marker). ON by default;
  the owner's manual fix turned into an automatic one-shot. Data only —
  reword it here.
- The **AI features block** (owner 2026-07-20, consumed by
  [AI Client & Flows](ai.md) and the GUI): `GEMINI_API_BASE` +
  `GEMINI_TEXT_MODEL` / `GEMINI_VISION_MODEL` (model names ROTATE with
  Google's releases — bump the strings here, never code),
  `GEMINI_KEY_SETTING` (the `settings.json` key name),
  `AI_STUDIO_URL` (the wizard's step-1 browser target),
  `AI_CALL_PAUSE_S` (free-tier pacing, ~10 requests/minute → 6.5 s
  between calls), `AI_TIMEOUT_S`, `AI_TEST_PROMPT` (the wizard's tiny
  Test call), the TRANSIENT-error retry knobs — `AI_TRANSIENT_STATUS`
  (`{429, 500, 503}`, the codes a wait can fix; everything else raises
  at once), `AI_RETRY_MAX` (attempts per call), `AI_RETRY_BACKOFF_S`
  (the fixed 503/500 wait) and `AI_RETRY_MAX_WAIT_S` (the cap on a
  429's server-named `retryDelay`) — `AI_MAX_QUESTIONS` + `SHEETS_DIR`
  + the four sheet-flow prompt templates (`AI_QUESTIONS_SYSTEM`,
  `AI_SHEET_SYSTEM`,
  `AI_SHEET_REQUEST`, `AI_REPAIR_PROMPT` — `{contract}` is
  instructions.md verbatim), and the checker's `AI_FLAGS_FILENAME`,
  `AI_CHECK_INSTRUCTIONS` (banal defects only, strict OK/DEFECTS
  format) and `AI_FIX_NOTE` (the re-send's per-item note). All prompt
  text is DATA — the owner rewords it here.
- `GEMINI_IMAGE_MODEL` (GUI rework Phase 18, [AI Client & Flows](ai.md)'s
  `generate_image`/`edit_image`) — the image-generation/edit model,
  separate from the free `GEMINI_TEXT_MODEL`/`GEMINI_VISION_MODEL`
  above. PAID-ONLY on the owner's key TODAY (every free-tier quota for
  this model reads `limit: 0` — see `AI_IMAGE_QUOTA_MARKERS` right
  below); Google retires this generation in October 2026 in favour of
  "Nano Banana 2" (`gemini-3.1-flash-image`) — bump the string then,
  nothing else names the model.
- `AI_IMAGE_QUOTA_MARKERS` (GUI rework Phase 18) — the free-tier-
  EXHAUSTED signal that makes a 429 PERMANENT
  (`ai.PaidFeatureRequired`) instead of transient: a tuple of AND-
  groups (every substring in a group must appear, case-insensitive;
  ANY group matching is enough), captured verbatim from the owner's
  real 429 body — `("free_tier", "limit: 0")` and `("check your plan
  and billing details",)`. Consumed by `ai._is_paid_quota_error`,
  which deliberately does NOT key on the same body's "retry in Xs"
  hint (present on both a permanent and an ordinary transient 429 —
  see ai.md's Design Decisions for the full trap writeup).
- `AI_IMAGE_PROBE_PROMPT`, `AI_IMAGE_GATE_MESSAGE` — GUI rework Phase
  19, [GUI](../gui.md)'s `ApiImageGenPanel`. `AI_IMAGE_PROBE_PROMPT` is
  the tiny, cheap prompt the panel's **Check API access** button sends
  through a REAL `ai.generate_image` call — the ONLY way to learn
  whether the account still has zero free-tier quota is to actually
  call the paid endpoint (same idea as the key wizard's own
  `AI_TEST_PROMPT` probing the free text model). `AI_IMAGE_GATE_MESSAGE`
  is the owner-facing copy shown — and the panel's Start button
  disabled — the moment that probe (or a live run, via
  `ApiImageAdapter.extract_image`'s own `PaidFeatureRequired` ->
  `driver.TerminalState` mapping) hits the free-tier-EXHAUSTED signal:
  "API image generation needs billing enabled — free tier limit is 0;
  use Website GEN for free." Data only — the owner rewords either here.
- `fmt_duration(seconds)`, `fmt_op_duration(seconds)`, `fmt_size(bytes)`,
  `fmt_pct(value)` — the short human formatters shared by the runner
  report and the GUI dashboard. `fmt_op_duration` keeps sub-second
  precision below 10 s (`0.2s`) for the fast in-place tools' per-image
  op times, where whole-second `fmt_duration` would show `0s`.
  `fmt_pct` (owner 2026-07-19) formats a tool metric % by magnitude —
  below 10 → 2 decimals (`0.08`, `5.23`, `9.99`), 10 and up → 1 decimal
  (`10.0`, `33.4`, `300.0`), the NUMBER only (callers append `%`) — so a
  3px crop reads `0.24%`, never a rounded-away `0%`. Used everywhere the
  tool panels render a % (the per-row column AND the header avg stat).
- `MIN_IMAGE_PX` — an `<img>` narrower than this is a placeholder.
- `PAUSE_POLL_INTERVAL_S` (owner 2026-07-21) — the poll granularity of
  the GUI's per-job Pause toggle wait ([Run Loop](runner.md)'s
  `wait_while_paused`, shared by [GUI](../gui.md)'s tool / AI-check
  worker loops). A plain top-level constant, not a `Timing` field — an
  internal wait-loop step, never a per-run/per-site tunable exposed in
  the UI (unlike `Timing.pause_min_s`/`pause_max_s`, the random PACING
  wait between prompts — a different, existing feature that shares the
  word "pause" but not the mechanism).

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
response as terminal). GUI rework Phase 17 (WEBSITE FIX, HIGH RISK /
owner-dependent): `attach_button` / `file_input` (both default `()`)
are the file-attach selectors [CDP Driver](driver.md)'s `submit_fix`
needs — the CSS selector(s) for the chat's attach/upload control and
the (often hidden-by-design) `<input type="file">` it drives. EMPTY
BY DEFAULT = WEBSITE FIX disabled for that site; `submit_fix` raises
`FixNotConfigured` immediately rather than guess. These are NOT
invented — the owner must capture them from the live DOM, the same
way every other selector on this page was captured, and paste them
into the site's block (the dataclass field carries a comment with the
exact CSS shape to paste).

`SITES` maps `chatgpt` / `gemini` to their blocks — both ship today
with WEBSITE FIX disabled (`attach_button=()`, `file_input=()`).
