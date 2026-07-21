"""PromptPainter configuration — every tunable value lives here.

Selectors rot with every site reskin: each DOM hook below is a tuple
of fallbacks tried in order, and when none match the driver FAILS
LOUDLY (root Rule #1) instead of guessing.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --- small formatters (shared by the runner and the GUI) -------------

def fmt_duration(seconds: float) -> str:
    """A short human duration: '3m 12s', '48s'."""
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def fmt_op_duration(seconds: float) -> str:
    """A short op duration for the fast in-place tools: '0.2s', '3.4s',
    '12s', '1m 05s'. Sub-second precision below 10s that the whole-second
    ``fmt_duration`` would flatten to '0s' (bg/crop/aspect run in
    fractions of a second; only upscale takes real time)."""
    if seconds < 10:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def fmt_size(num_bytes: int) -> str:
    """A short human file size: '1.4 MB', '812 KB', '70 B'."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / 1_048_576:.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


def fmt_pct(value: float) -> str:
    """A tool metric percentage, precision scaled by magnitude (owner
    2026-07-19): below 10 -> 2 decimals ('0.08', '5.23', '9.99'), 10 and
    up -> 1 decimal ('10.0', '33.4', '300.0'). Returns the NUMBER only;
    callers append the '%'. So a 3px crop reads '0.24', never a rounded-
    away '0'."""
    return f"{value:.2f}" if value < 10 else f"{value:.1f}"

# --- CDP attachment / Chrome launch ----------------------------------

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Where chrome.exe usually lives; the launcher tries these in order.
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# Chrome 136+ refuses --remote-debugging-port on the DEFAULT profile,
# so PromptPainter launches Chrome with its own profile folder. The
# owner logs in ONCE there (Google + OpenAI); sessions persist.
CHROME_PROFILE_DIR = PROJECT_ROOT / "chrome-profile"

# launch -> the CDP endpoint must answer within this window
CHROME_LAUNCH_TIMEOUT_S = 30.0

# --- Output ----------------------------------------------------------

# The out/ folder MIRRORS the DOMY assets/ tree so the owner can copy
# its whole content straight into assets/ (owner 2026-07-18). Sheets
# carry site-agnostic FULL drop paths ("assets/emblem/mood/Glory.png");
# the site is injected after the category:
#     assets/<category>/<rest>  ->  <out>/<category>/<site>/<rest>
# Legacy relative drops keep the old layout: <out>/<site>/<drop>.
# Run state and reports live OUT of the copyable tree, under
# <out>/_state/<site>/; backup variants land under <out>/EXTRA/.
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"
STATE_DIRNAME = "_state"
REPORT_SUFFIX = "_report.txt"


def dest_for(drop_path: str, site_key: str) -> str:
    """The save path (relative to the out base) for one drop path."""
    parts = drop_path.split("/")
    if parts[0] == "assets" and len(parts) >= 3:
        category, rest = parts[1], parts[2:]
        return "/".join([category, site_key, *rest])
    return "/".join([site_key, drop_path])

# --- The sheet contract ----------------------------------------------

# The arrow line must name a file with one of these extensions.
IMAGE_EXTENSIONS = (".png",)

# A bold span matching this marks an entry (or a whole section) as
# skipped — logged, never generated.
SKIP_MARKER_PATTERN = r"\bREUSE\b|\bSUPERSEDED\b|\bDO[\s-]+NOT[\s-]+GENERATE\b"

# --- Postprocess: background removal + crop (owner workflow step 6) --

# painter/postprocess.py runs over every saved image; the two steps
# are COMPOSABLE (owner's #7): remove_background auto-detects per
# file (already-transparent -> nothing, white/black cleared,
# ambiguous -> unclear, left untouched); crop_transparent autocrops
# a transparent image to its content bounding box.
CROP_MARGIN_PX = 4  # safety margin kept around the content box

# CHANGED vs SKIPPED by EXACT resolution (owner 2026-07-19, reverses the
# old CROP_MIN_TRIM_PX slop): crop_transparent counts a crop as soon as
# the cropped output differs from the input by >= 1px on ANY side — a
# 1254x1254 -> 1254x1251 3px trim IS a crop even though its % rounds
# tiny. Only a 0px change (output size == input size) is SKIPPED. There
# is no negligible-trim threshold any more.

# INK-BASED content box (owner 2026-07-18, the OldAge.png case). A
# single-threshold box (any pixel at alpha >= 8) was defeated by faint
# stray pixels hugging the border (a thin far-left line at alpha ~8-32),
# so the crop trimmed almost nothing. Instead a row/column counts as
# content only when it holds at least CROP_MIN_INK_PX pixels that are at
# least CROP_INK_ALPHA opaque: a sparse faint line no longer extends the
# box, while a genuinely wide soft region still registers.
CROP_INK_ALPHA = 40   # alpha >= this counts as a solid "ink" pixel
CROP_MIN_INK_PX = 3   # a row/col needs this many ink pixels to be content

# CONSERVATIVE EDGE-HALO CLEANUP (owner 2026-07-18). Before cropping,
# faint pixels (alpha < CLEAN_EDGE_ALPHA) that are CONNECTED TO THE IMAGE
# BORDER — the visible stray line / halo in the transparent frame — have
# their alpha zeroed. Interior soft edges are enclosed by the solid
# subject, never border-connected, and stay untouched. This is NOT a
# global alpha[alpha<K]=0 (that would nibble genuine soft edges).
CLEAN_EDGE_ALPHA = 40     # faint pixels below this may be border halo
CLEAN_EDGE_ENABLE = True  # run the border-connected cleanup before crop

# BLACK-VOID REMOVAL + SAFETY GUARD (owner 2026-07-19, the bible/dark
# case). Brightness-keying cannot separate a DARK subject from a black
# background, so the old "biggest bright blob" black remover ate the
# dark stone frame and dark regions of dark stained-glass rondels
# (50-78% turned transparent — swiss cheese). Two defences:
#
#  - BLACK_VOID_MAX: the black remover clears ONLY near-black pixels
#    that are CONNECTED TO THE IMAGE BORDER (the corner void), reusing
#    the same border-connected flood as the white path. Interior dark
#    regions ENCLOSED by the subject (the black leading between glass,
#    dark inner areas) are never border-connected and stay OPAQUE.
#    Tuned against the 7 destroyed bible/dark rondels: their corner
#    void is brightness 0-2 but their dark subject/frame is only 5-12,
#    so keying can't tell them apart — at ANY threshold the flood leaks
#    along the dark ring into the subject. 14 is chosen so those leaky
#    rondels clear the guard below and BAIL (removed >= 0.45), while a
#    genuine bright subject on black stays ~0.24 (only the corners) and
#    processes; the guard, not this threshold, is what protects a frame.
#
#  - SAFETY_MAX_REMOVE_FRAC: if a removal would clear more than this
#    fraction of the image, ABORT — do NOT save, leave the ORIGINAL
#    untouched, report loudly. A rondel whose dark frame is TANGENT to
#    the edge lets the flood leak along the ring and over-remove; the
#    guard catches exactly those. Tradeoff (owner accepts): a genuinely
#    SMALL bright subject on a huge void would also exceed the guard and
#    be left untouched — fine on BLACK because every dark-void asset is
#    a medallion/rondel/window that FILLS the frame, so a large removal
#    almost always means "ate the subject". Bright-on-black legit plates
#    clear only ~0.24 (the corners), well under 0.40; the 7 destroyed
#    dark rondels clear 0.45-0.62, so they bail.
#
#  PER-PATH thresholds (owner's guard is "general", but the two paths
#  have very different legit backgrounds — measured over the 531 real
#  outputs, 2026-07-19). The "never destroy" PRINCIPLE applies to both;
#  the NUMBER cannot: a single 0.40 would wrongly bail most white plates.
#    * BLACK path -> SAFETY_MAX_REMOVE_FRAC (0.40). Legit bright-on-black
#      clears ~0.24; dark-rondel destruction is 0.45+. Clean separation.
#    * WHITE path -> SAFETY_MAX_REMOVE_FRAC_WHITE (0.85). Legit white
#      BACKGROUNDS are routinely large and clean: the 24 real white
#      plates clear 0.33-0.57 (median 0.44) with the subject fully
#      intact (e.g. a circular badge on a white margin). Guarding white
#      at 0.40 would FALSE-bail 58% of them. 0.85 sits well above that
#      legit ceiling, so it fires only on a catastrophic white-subject-
#      eaten (flood devoured a near-white image) — never on a clean
#      background removal.
BLACK_VOID_MAX = 14                  # brightness <= this AND border-connected = void
SAFETY_MAX_REMOVE_FRAC = 0.40        # BLACK path: clearing more than this -> abort
SAFETY_MAX_REMOVE_FRAC_WHITE = 0.85  # WHITE path: legit backgrounds reach ~0.57


# --- Upscale (owner's #13) -------------------------------------------

# Real-ESRGAN via the standalone realesrgan-ncnn-vulkan Windows
# binary. It lives under tools/realesrgan/ (gitignored, downloaded
# on first use from the official GitHub release).
TOOLS_DIR = PROJECT_ROOT / "tools"
UPSCALE_DIR = TOOLS_DIR / "realesrgan"
UPSCALE_EXE_NAME = "realesrgan-ncnn-vulkan.exe"
UPSCALE_ZIP_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
)
# Model (owner research 2026-07-21): the anime-6B net is ART-TUNED for
# flat-colour / cell-shaded illustration — this project's stained-glass
# rondels and badges — where the general-purpose x4plus over-smooths fine
# linework. A/B-verified live (realesrgan-ncnn-vulkan -n <model> -s 4) on
# a real 592x592 output (a Greek-pantheon rondel): x4plus-anime showed
# visibly crisper eye/hair/line detail, higher edge energy (Laplacian
# variance ~328 vs ~264), no colour shift (<1/255 mean RGB delta) or
# banding regression, a smaller PNG, and ran ~2.4x faster (3.3s vs 8.0s).
# Flip back to "realesrgan-x4plus" if a future asset style suits the
# smoother general-purpose net better.
UPSCALE_MODEL = "realesrgan-x4plus-anime"
# Gating (owner 2026-07-19, four editable params at the ENGINE level —
# painter/upscale.py's upscale_if_small signature/defaults are UNCHANGED
# by the GUI rework). An image qualifies ONLY if its aspect ratio W/H is
# within [UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX] (the circular/badge
# class) AND (W < UPSCALE_MIN_WIDTH OR H < UPSCALE_MIN_HEIGHT); then it
# is upscaled (native 4x + LANCZOS, aspect preserved) so W >=
# UPSCALE_MIN_WIDTH and H >= UPSCALE_MIN_HEIGHT. The defaults (800 / 800
# / 0.9 / 1.1) are the old min_px=800 + aspect_tol=0.1 behaviour.
#
# GUI rework Phase 6: the GUI no longer exposes min_width/min_height as
# TWO separate fields — a single min-SIDE spinner drives both (see
# UPSCALE_MIN_SIDE_DEFAULT below), and the aspect band is authored via
# an embedded FilterEditor condition instead of dedicated aspect-from/
# aspect-to fields (gui.py's AgentPanel/UpscaleParamsDialog and
# gui._upscale_params_from_side_and_filter). These four stay the
# ENGINE's own defaults, read by upscale_if_small's signature, main.py's
# CLI, and the GUI's migration of an owner's pre-Phase-6 settings.json.
UPSCALE_MIN_WIDTH = 800
UPSCALE_MIN_HEIGHT = 800
UPSCALE_ASPECT_MIN = 0.9
UPSCALE_ASPECT_MAX = 1.1
# GUI spinner step for the upscale gate's min-side field (Rule #4).
UPSCALE_MINDIM_STEP = 50  # min-side spinner step (px)
# GUI rework Phase 6: the per-agent AND standalone upscale gate collapse
# min WIDTH + min HEIGHT into ONE min-SIDE spinner (both axes must reach
# the same minimum now, gated separately by an embedded FilterEditor —
# see gui.py's AgentPanel/UpscaleParamsDialog and
# gui._upscale_params_from_side_and_filter). This is that spinner's seed
# default; reuses UPSCALE_MIN_WIDTH's value (== UPSCALE_MIN_HEIGHT
# already, by design) so the shipped default behaves byte-identically
# to the old four-field gate.
UPSCALE_MIN_SIDE_DEFAULT = UPSCALE_MIN_WIDTH


# --- Change aspect ratio (owner's batch deform tool, 2026-07-19) -----

# painter/aspect.py DEFORMS every image in a folder to a target ratio
# X:Y in place — a non-proportional LANCZOS STRETCH (intended). The
# rule NEVER shrinks either dimension: the result is the smallest box
# of the target ratio that still CONTAINS the original, so exactly ONE
# axis grows and neither is cut. An image whose current W/H is within
# ASPECT_TOL of the target ratio is already at ratio and left BYTE-
# UNCHANGED (no write). The GUI's ratio prompt defaults to 16:9.
ASPECT_TOL = 0.001
ASPECT_DEFAULT_W = 16
ASPECT_DEFAULT_H = 9

# Optional INPUT FILTER on the aspect tool (owner 2026-07-19). Before
# deforming, an image's CURRENT ratio W/H can gate whether it is touched
# at all: a single [from, to] range plus a MODE — off (process all) / IF
# (process ONLY images whose W/H is IN the range) / IF NOT (SKIP those,
# process the rest). Example bands: ~square = 0.9-1.1; 2:1 = ~1.8-2.2.
# A filtered-out image is a plain SKIP ("nothing", no backup). The mode
# strings double as the dialog's combobox labels (Rule #4).
ASPECT_FILTER_OFF = "off"
ASPECT_FILTER_IF = "IF"
ASPECT_FILTER_IF_NOT = "IF NOT"
ASPECT_FILTER_MODES = (ASPECT_FILTER_OFF, ASPECT_FILTER_IF, ASPECT_FILTER_IF_NOT)
# the dialog pre-fills this ~square band the first time the filter is used
ASPECT_FILTER_DEFAULT_FROM = 0.9
ASPECT_FILTER_DEFAULT_TO = 1.1

# GUI rework Phase 5 — the visual aspect-ratio editor's live label shows
# the TARGET ratio in two forms at once: the exact decimal (owner
# decision 2026-07-21, standard ROUNDING — 16:9 -> "1.778:1") beside the
# smallest-integer form (`reduced_ratio`, gcd-based — 1920x1080 -> 16:9).
# Both pure functions live in aspect.py; this constant is their shared
# default precision, kept in config.py (Rule #4) so it is tunable in one
# place and importable with no tkinter dependency.
ASPECT_LABEL_DECIMALS = 3

# --- Shared filter framework (owner decision 2026-07-21) --------------
#
# GUI rework Phase 3: ONE stackable "what should this tool touch" gate
# meant to eventually replace every tool's bespoke filter — the Aspect-
# only ASPECT_FILTER_* scalar just above, and Upscale's four-field
# aspect/size gate — with a single reusable shape. The matching LOGIC
# lives in painter/filters.py (`FilterCondition` + `matches()`, pure/
# engine-side, no GUI import); this block only holds the stable
# identifier strings a condition's `kind`/`polarity` fields are built
# from, so the engine, the tests and the future GUI widget all name the
# same five kinds and two polarities. Migrating the existing tools onto
# this framework is a LATER phase — nothing here is wired into a tool
# yet (Phase 3 only adds the engine + these constants).
#
# Five kinds, each a [lo, hi] band tested against one image measurement
# (see filters.py's docstring for the exact per-kind math): the aspect
# ratio W/H (EXACT — lo==hi pins a single target point; RANGE — a typed
# band, IDENTICAL comparison, only the GUI authoring differs), ANY_SIDE
# (both W and H at once, orientation-agnostic — every side must sit in
# the band), and the raw WIDTH/HEIGHT in pixels (orientation matters).
# FILTER_KINDS is the ordered tuple the GUI's kind combobox will list;
# the values ARE the display text (owner 2026-07-21: same convention as
# ASPECT_FILTER_MODES above / STYLE_CHOICES below — Rule #4 strings do
# double duty as UI labels, no separate label table).
FILTER_KIND_ASPECT_EXACT = "Aspect (exact)"
FILTER_KIND_ASPECT_RANGE = "Aspect (range)"
FILTER_KIND_ANY_SIDE = "Any side"
FILTER_KIND_WIDTH = "Width"
FILTER_KIND_HEIGHT = "Height"
FILTER_KINDS = (
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_ANY_SIDE,
    FILTER_KIND_WIDTH,
    FILTER_KIND_HEIGHT,
)

# a condition PASSES when its measurement is IN [lo, hi] (IF) or OUT of
# it (IF NOT) — same two words and spelling as the legacy
# ASPECT_FILTER_IF / ASPECT_FILTER_IF_NOT above, so a future migration
# reads old mode strings straight across with no translation table.
FILTER_POLARITY_IF = "IF"
FILTER_POLARITY_IF_NOT = "IF NOT"

# the settings.json key a saved STACK of conditions (a reusable preset,
# e.g. "square badges only") will live under once the GUI grows preset
# save/load (Phase 4). Reserved here so the name is decided once, ahead
# of the GUI work that reads/writes it.
FILTER_PRESETS_SETTING = "filter_presets"

# GUI rework Phase 4 (fixes Phase 3's flagged caveat): a pinned "Aspect
# (exact)" condition is a razor-thin `lo == hi` float-equality test —
# correct for the engine (see filters.py's "no hidden epsilon" design
# decision) but useless authored raw, since a REAL decoded image's
# width/height division almost never lands on that exact double (a
# "square" export at 1000x1001 divides to 0.999000999..., not 1.0).
# The GUI's FilterEditor widget authors this kind from a SINGLE typed
# ratio and widens it into the band [ratio - tol, ratio + tol] before
# building the FilterCondition, so ordinary near-square exports still
# match; `matches()` itself is unchanged — this only affects what the
# widget WRITES into a condition's lo/hi for this one kind.
FILTER_ASPECT_EXACT_TOL = 0.02


# --- Settings persistence (owner's #9) -------------------------------

# The GUI's remembered choices; JSON at the project root, gitignored.
# What goes in the dict is the GUI's business — this is just the home.
SETTINGS_PATH = PROJECT_ROOT / "settings.json"


# --- GUI themes: the single source of truth (owner 2026-07-18) -------
#
# TWO coordinated palettes flipped as one by the GUI's Day/Night
# switch. This block is PURE DATA (hex strings only) so the engine and
# every test can import config.py without pulling in tkinter /
# ttkbootstrap. gui.py turns each entry into the two backbones:
#   - `ttk`   -> the 16 ttkbootstrap colour keys. "night" is the
#               built-in darkly theme written out VERBATIM (the owner
#               is happy with it); "day" is a custom light theme
#               ("painter_day") mapped from the owner's website LIGHT
#               palette, authored to how THIS app actually uses each
#               key. Two keys are deliberately repurposed: `dark` is a
#               LIGHT surface on day (#e8e4dd) because the app uses it
#               only as the combobox-dropdown / hover / code-box
#               background, and `light` is a MID grey (#888888) because
#               the app uses it only as a muted-text / outline
#               foreground, never as a light fill.
#   - `status`-> the semantic colours that are set PER WIDGET at
#               construction (Select-tree leaf rows, DocWindow text
#               tags) and so must be recomputed on a flip; contrast-
#               tuned for each background.
#   - `ttkname`/`mode`/`switch_on` -> the ttkbootstrap theme name, the
#               customtkinter appearance mode, and the switch knob side
#               (False = left/moon, True = right/sun).
THEMES = {
    "night": {
        "ttkname": "darkly",
        "mode": "dark",
        "switch_on": False,
        "ttk": {
            "primary": "#375a7f",
            "secondary": "#444444",
            "success": "#00bc8c",
            "info": "#3498db",
            "warning": "#f39c12",
            "danger": "#e74c3c",
            "light": "#ADB5BD",
            "dark": "#303030",
            "bg": "#222222",
            "fg": "#ffffff",
            "selectbg": "#555555",
            "selectfg": "#ffffff",
            "border": "#222222",
            "inputfg": "#ffffff",
            "inputbg": "#2f2f2f",
            "active": "#1F1F1F",
        },
        "status": {
            "done": "#00bc8c",       # green — finished (darkly success)
            "done_soft": "#9ccc65",  # olive — done on one site only
            "advice": "#f39c12",     # orange — sheet advice (warning)
            "superseded": "#e74c3c",  # red — superseded (danger)
            "code_fg": "#a5d6ff",    # DocWindow code text on dark box
            "btn_text": "#ffffff",   # solid-button label
            "skip": "#adb5bd",       # muted grey — SKIPPED tool rows (dimmed)
            "toolchanged": "#2ee59d",  # bright mint-teal — CHANGED tool rows (POPS)
        },
    },
    "day": {
        "ttkname": "painter_day",
        "mode": "light",
        "switch_on": True,
        "ttk": {
            "primary": "#a8873d",    # accent gold
            "secondary": "#6b6456",  # warm grey
            "success": "#1a8f6a",    # Start
            "info": "#8a6f32",       # accent-dark (headers + fills)
            "warning": "#b9770e",
            "danger": "#c0392b",     # Stop
            "light": "#888888",      # MID grey — muted/outline foreground
            "dark": "#e8e4dd",       # LIGHT surface — dropdown/hover/code bg
            "bg": "#f5f2ed",         # cream window
            "fg": "#1a1a1a",         # text-primary
            "selectbg": "#a8873d",   # gold selection
            "selectfg": "#ffffff",
            "border": "#d4d0c8",
            "inputfg": "#1a1a1a",
            "inputbg": "#ffffff",    # white fields
            "active": "#e8e4dd",     # border-light
        },
        "status": {
            "done": "#1a8f6a",
            "done_soft": "#6f8f2f",
            "advice": "#b9770e",
            "superseded": "#c0392b",
            "code_fg": "#1f5b9e",    # legible on the light code surface
            "btn_text": "#ffffff",
            "skip": "#8a8578",       # muted warm grey — SKIPPED tool rows
            "toolchanged": "#0a9d6e",  # vivid emerald — CHANGED tool rows (POPS on cream)
        },
    },
}


def theme_pair(key: str) -> tuple[str, str]:
    """A CustomTkinter (light, dark) colour tuple for one ttk palette
    key — day is the light end, night the dark end. Passing every CTk
    colour as this tuple lets a single ctk.set_appearance_mode() repaint
    every CTk control on a flip with zero re-walk."""
    return (THEMES["day"]["ttk"][key], THEMES["night"]["ttk"][key])


def status_pair(role: str) -> tuple[str, str]:
    """The (light, dark) tuple for one semantic STATUS role — for the
    few CTk colours (solid-button text) that come from the status block
    rather than the ttk palette."""
    return (THEMES["day"]["status"][role], THEMES["night"]["status"][role])


# --- Solid-button fills per theme (owner 2026-07-19) -----------------
#
# The SOLID button kinds each carry their OWN (day, night) fill + text,
# decoupled from the ttk palette so the DAY shade can differ from NIGHT
# for every kind (owner's ask) without disturbing the palette keys that
# also serve borders / muted text. Two rules the owner set:
#   * DAY has NO dark-filled neutral button — `secondary` becomes a
#     LIGHT sand fill with dark text (it used to borrow the dark warm-
#     grey palette key and render brown on the cream window).
#   * Every kind's DAY hex DIFFERS from its NIGHT hex; DAY shades are a
#     touch lighter / desaturated to sit on the cream window, NIGHT
#     keeps the darkly look.
# Coloured kinds stay clearly coloured in both themes (white label);
# only the neutral kind flips to a light fill + dark label on day.
BUTTON_FILL = {
    "secondary": ("#e6e0d3", "#4a4a4a"),  # day: light sand   / night: neutral grey
    "success":   ("#1f9d76", "#00bc8c"),  # day: softer green / night: darkly green
    "danger":    ("#cf4436", "#e74c3c"),  # day: brick red    / night: darkly red
    "info":      ("#9a7d3a", "#3aa0e0"),  # day: accent gold  / night: sky blue
}
BUTTON_TEXT = {
    "secondary": ("#2a2620", "#ffffff"),  # DARK text on the light day fill
    "success":   ("#ffffff", "#ffffff"),
    "danger":    ("#ffffff", "#ffffff"),
    "info":      ("#ffffff", "#ffffff"),
}


def button_fill_pair(kind: str) -> tuple[str, str]:
    """(day, night) fill for one SOLID button kind — a CTk light/dark
    tuple that auto-flips on set_appearance_mode()."""
    return BUTTON_FILL[kind]


def button_text_pair(kind: str) -> tuple[str, str]:
    """(day, night) label colour for one SOLID button kind — dark on the
    light day fill for the neutral kind, white on the coloured ones."""
    return BUTTON_TEXT[kind]


# --- Multi-file selection base (aspect tool, owner 2026-07-19) --------
#
# The Aspect-ratio tool picks INDIVIDUAL image FILES (a folder may hold
# mixed ratios), unlike the folder-based BG / Crop / Upscale tools. The
# job machinery keys every file by a (base folder, relative path) pair —
# JobTemp backs up under base/rel and the panel groups rows by rel's
# parent. This derives that base (the common ancestor of the picks) and
# each file's rel, so a selection spanning sub-folders still groups and
# restores correctly. Files sitting in ONE folder yield base=that folder
# and rel=filename.
def selection_base_and_rels(paths) -> tuple:
    """Return ``(base, [rel, ...])`` for a list of selected file paths:
    ``base`` is the common ancestor DIRECTORY of the picks and each
    ``rel`` is the POSIX path of the file relative to it. Raises
    ``ValueError`` on an empty selection (nothing to base)."""
    import os
    from pathlib import Path

    files = [Path(p) for p in paths]
    if not files:
        raise ValueError("empty selection — no files to base")
    if len(files) == 1:
        base = files[0].parent
    else:
        base = Path(os.path.commonpath([str(f.parent) for f in files]))
    rels = [f.relative_to(base).as_posix() for f in files]
    return base, rels


# The image extensions the four in-place tools accept — ONE home for the
# folder walk (iter_images) and the aspect file-picker filter (Rule #4/#5).
TOOL_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def iter_images(folder) -> list:
    """Every image FILE under ``folder`` (recursive), sorted — the shared
    enumerator behind the folder-based tools (BG / Crop / Upscale) and the
    Aspect tool's folder input. Non-image files are skipped."""
    from pathlib import Path

    root = Path(folder)
    return sorted(
        p for p in root.rglob("*")
        if p.suffix.lower() in TOOL_IMAGE_EXTENSIONS
    )


def iter_md_files(folder) -> list:
    """Every ``.md`` FILE under ``folder`` (recursive), sorted — mirrors
    ``iter_images``. Backs the Collections queue's "Add folder…" button:
    point it at a folder of prompt sheets and every sheet underneath,
    however nested, is queued."""
    from pathlib import Path

    root = Path(folder)
    return sorted(root.rglob("*.md"))


# --- Dashboard per-JOB panels (owner 2026-07-19) ---------------------
#
# The dashboard shows one panel PER RUNNING JOB (up to 6 in parallel):
# the two image-generation SITES plus the four in-place TOOLS, each its
# own worker thread and its own panel. A panel appears when its job
# starts and gets a CLOSE button when it finishes; the grid re-flows by
# how many are active. JOB_ORDER is the FIXED priority (gen first) that
# places panels row-major into the grid, so ChatGPT + Gemini always take
# the top cells. All of this is PURE data (strings/numbers only) so the
# engine and tests import config.py without tkinter.
JOB_ORDER = ("chatgpt", "gemini", "bg", "crop", "upscale", "aspect", "aicheck")
JOB_TOOL_KINDS = ("bg", "crop", "upscale", "aspect")

# button + panel-header label per job (the three tool buttons drop the
# old "only…" wording, owner 2026-07-19)
JOB_LABEL = {
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
    "bg": "BG removal",
    "crop": "Crop",
    "upscale": "Upscale",
    "aspect": "Aspect ratio",
    "aicheck": "AI check",
}

# EVERY job carries an icon (assets/icons/<stem>) beside its coloured
# NAME on the tool button + panel header: the two gen sites their brand
# logo, the four tools the owner's dedicated PNG icons (owner 2026-07-19,
# replacing the old emoji marks). gui.icon() resolves each stem — svg
# where Qt can render it, png otherwise (the tool icons ARE png), so the
# stems double as the png basenames. Supersedes the old gui._SITE_ICON.
JOB_LOGO = {
    "chatgpt": "chatGPT",
    "gemini": "gemini",
    "bg": "bg",
    "crop": "crop",
    "upscale": "upscale",
    "aspect": "aspect",
    "aicheck": "ai",
}

# per-job (day, night) colour pair — the header name + the tool button
# fill. CTk stores the tuple and re-resolves it per appearance mode, so
# a Day/Night flip recolours them with no re-walk.
JOB_COLORS = {
    "chatgpt": ("#1a8f6a", "#00bc8c"),  # green
    "gemini": ("#2f6fb0", "#4a9eff"),   # blue
    "bg": ("#0f8f8f", "#2fd4d4"),       # cyan / teal
    "crop": ("#b9770e", "#f0a835"),     # amber
    "upscale": ("#7a4fc0", "#b088f0"),  # violet
    "aspect": ("#b03080", "#e05ab0"),   # magenta
    "aicheck": ("#b23a55", "#f26d8d"),  # rose / red
}

# the aggregate metric each TOOL panel reports (its per-image % means):
#   bg = removed pixels, crop = area reduction, upscale = area increase,
#   aspect = deformation (growth of the stretched axis). measure() tags
#   every item with the same word so the panel header and the rows agree.
# "aicheck" is the odd one out: its per-row metric is the DEFECT COUNT,
# not a %, but the word still names the column for panel/doc coherence.
JOB_METRIC = {
    "bg": "removed",
    "crop": "reduction",
    "upscale": "increase",
    "aspect": "deformation",
    "aicheck": "defects",
}


def job_color_pair(kind: str) -> tuple[str, str]:
    """The (day, night) colour pair for one job kind — a CTk light/dark
    tuple that auto-flips on set_appearance_mode()."""
    return JOB_COLORS[kind]


# how many grid COLUMNS for N active panels; rows = ceil(N / cols). The
# owner's chosen shape: 1→1, 2→2, 3→3, 4→2x2, 5→2x3 (ChatGPT+Gemini in
# the top row, 6th cell empty), 6→2x3; 7 (all six + AI check) → 3x3.
GRID_COLS_BY_COUNT = {1: 1, 2: 2, 3: 3, 4: 2, 5: 2, 6: 2, 7: 3}


# --- Dashboard status badges (owner 2026-07-20) ----------------------
#
# Small coloured DOT badges beside an image's name in the gen panels'
# Collections tree, marking what actually HAPPENED to that image: a
# post-save step earns its badge ONLY when it really CHANGED the file
# (status "done" in the runner's action string — never a "nothing" /
# "unclear"), and "retry" marks an image that needed the one-shot SAFER
# RETRY to generate. PURE DATA — the owner retints/renames here; order =
# render order. The colours are deliberately THEME-AGNOSTIC mid-tones
# (like the CHECKER greys) so one dot reads on both the dark and the
# cream tree background. NOTE: the dots are PIL-DRAWN, not emoji — Tk
# 8.6 on Windows renders colour emoji as identical monochrome circles
# (verified live 2026-07-20), so glyph badges cannot be told apart.
BADGES = {
    "bg": ("#22c55e", "BG removed"),      # green
    "crop": ("#f59e0b", "cropped"),       # orange
    # GUI rework Phase 8: the new Force-Aspect pipeline step. Reuses the
    # SAME magenta hue JOB_COLORS already ties to "aspect" everywhere
    # else in the app (the tool button, the AspectRatioCanvas accent),
    # picked from the same Tailwind-500 family the other three badges
    # already come from (fuchsia-500 — bg/crop/upscale/retry are green
    # -500/amber-500/blue-500/purple-500) so it reads as ONE consistent
    # palette, not an unrelated new hue.
    "aspect": ("#d946ef", "aspect forced"),  # magenta/fuchsia
    "upscale": ("#3b82f6", "upscaled"),   # blue
    "retry": ("#a855f7", "safer retry"),  # purple
}
# how the runner's post_save action string spells each step
# ("REMOVE BG: done, CROP: done, ASPECT: done, UPSCALE: nothing") ->
# badge key. "ASPECT" is the Force-Aspect step (GUI rework Phase 8,
# painter.aspect.change_aspect run over the just-saved image).
BADGE_ACTION_STEPS = {
    "REMOVE BG": "bg",
    "CROP": "crop",
    "ASPECT": "aspect",
    "UPSCALE": "upscale",
}
BADGE_DONE_STATUS = "done"  # the only status that earns a badge
# dot geometry (the GUI rasterizes at BADGE_DOT_SS x then LANCZOS-downs)
BADGE_DOT_PX = 9    # final dot diameter
BADGE_DOT_GAP_PX = 3  # gap between dots (and before the first)
BADGE_DOT_SS = 4    # supersample factor for a crisp anti-aliased rim


def badge_keys_for(actions: str, retried: bool = False) -> tuple:
    """The badge keys one image earned, in BADGES (render) order.

    ``actions`` is the runner's post_save description ("REMOVE BG:
    done, CROP: done, UPSCALE: nothing"); a step counts only when its
    status is exactly BADGE_DONE_STATUS. ``retried`` adds the safer-
    retry badge. Unknown segments ("POSTPROCESS: FAILED", free text)
    are simply ignored — badges only ever assert a positive."""
    earned = set()
    for part in actions.split(","):
        step, _, status = part.partition(":")
        key = BADGE_ACTION_STEPS.get(step.strip())
        if key is not None and status.strip() == BADGE_DONE_STATUS:
            earned.add(key)
    if retried:
        earned.add("retry")
    return tuple(key for key in BADGES if key in earned)


# --- Main Menu (GUI rework Phase 10) ----------------------------------
#
# The startup landing screen: ONE big tile per functionality, replacing
# "everything visible at once" (the old always-shown queue/agents/tool
# toolbar) as the first thing the owner sees. PURE DATA — a frozen
# dataclass + tuple, the same shape as SiteConfig/SITES below — so a
# test asserts coverage/uniqueness with no tkinter import; gui.MainMenu
# is the only thing that turns an entry into a widget (a tile factory,
# not one block per tile). Card radius sits in DESIGN.md's "cards,
# panels: 12-16px" bracket, one notch above the smaller "buttons,
# inputs" bracket gui.py's own BTN_RADIUS/INPUT_RADIUS already use.
MENU_TILE_RADIUS = 16          # owner decision 2026-07-21
MENU_TILE_COLS = 4             # 4x2 grid for today's 8 tiles
MENU_TILE_W = 180              # minimum tile width, px (grid stretches wider)
MENU_TILE_H = 140              # minimum tile height, px
MENU_TILE_GAP_PX = 16          # gap between tiles (DESIGN.md 8pt grid, 2 units)
MENU_TILE_ICON_PX = 40         # icon side inside a tile (ICON_TARGET_PX=20 is
#                                 the smaller button-icon size, gui.py-local)
MENU_TILE_BORDER_PX = 2        # accent border width, at rest
MENU_TILE_BORDER_HOVER_PX = 4  # accent border width, hovered (the one thing
#                                 that changes on hover — see gui.MainMenu)


@dataclass(frozen=True)
class MenuTile:
    """One Main Menu tile. ``id`` is what ``PainterGui._select_tile``
    switches on to reach the EXISTING handler each functionality
    already had before Phase 10 — this dataclass only decides what the
    tile looks like, never what picking it DOES."""

    id: str
    label: str
    description: str          # one line, shown under the label
    icon: str                 # assets/icons stem (gui.icon() resolves it)
    color: tuple[str, str]    # (day, night) accent hex pair
    enabled: bool = True      # False = shown, greyed out, not clickable


MENU_TILES: tuple[MenuTile, ...] = (
    # spans BOTH gen sites, not one job — no single JOB_COLORS entry
    # fits, so this gets its own accent (indigo)
    MenuTile(
        id="website_gen", label="Website GEN",
        description=(
            "Drive your logged-in ChatGPT/Gemini tabs to generate a"
            " collection"
        ),
        icon="web", color=("#4338ca", "#818cf8"),
    ),
    MenuTile(
        id="ai_sheet_gen", label="New collection (AI)",
        description="Ask Gemini to draft a new prompt sheet from a request",
        icon="ai", color=("#a16207", "#facc15"),  # yellow
    ),
    # Phase 19 wires the adapter + panel; shown greyed-out until then
    MenuTile(
        id="api_image_gen", label="API Image GEN",
        description="Generate images via the paid Gemini API — coming soon",
        icon="gemini", color=("#c2410c", "#fb923c"),  # orange
        enabled=False,
    ),
    MenuTile(
        id="image_checker", label=JOB_LABEL["aicheck"],
        description="Vision pass over a folder — flags banal defects",
        icon=JOB_LOGO["aicheck"], color=JOB_COLORS["aicheck"],
    ),
    MenuTile(
        id="bg", label=JOB_LABEL["bg"],
        description="Remove the background from every image in a folder",
        icon=JOB_LOGO["bg"], color=JOB_COLORS["bg"],
    ),
    MenuTile(
        id="crop", label=JOB_LABEL["crop"],
        description="Autocrop every image to its content box",
        icon=JOB_LOGO["crop"], color=JOB_COLORS["crop"],
    ),
    MenuTile(
        id="upscale", label=JOB_LABEL["upscale"],
        description="Upscale small images with Real-ESRGAN",
        icon=JOB_LOGO["upscale"], color=JOB_COLORS["upscale"],
    ),
    MenuTile(
        id="aspect", label=JOB_LABEL["aspect"],
        description="Force every image in a folder to one aspect ratio",
        icon=JOB_LOGO["aspect"], color=JOB_COLORS["aspect"],
    ),
)

# which JOB_ORDER kind(s) each MENU_TILES id represents — the running
# view's IconBar (GUI rework Phase 11) reads this to decide whether a
# tile is currently "live" (config.JOB_COLORS-tinted) vs idle: a
# running job's kind is checked against ITS tile's entry here, never
# the other way around, so a new job kind never needs an IconBar code
# change, only a data one. "website_gen" is the one tile spanning TWO
# kinds (it lights up while EITHER site runs); the two AI dialogs
# (`ai_sheet_gen`/`api_image_gen`) have no dashboard job of their own,
# hence the empty tuples — they never light up, only ever launch.
TILE_JOB_KINDS: dict[str, tuple[str, ...]] = {
    "website_gen": ("chatgpt", "gemini"),
    "ai_sheet_gen": (),
    "api_image_gen": (),
    "image_checker": ("aicheck",),
    "bg": ("bg",),
    "crop": ("crop",),
    "upscale": ("upscale",),
    "aspect": ("aspect",),
}


def tile_for_kind(kind: str) -> str | None:
    """The ONE ``MENU_TILES`` id that is kind's OWN persistent-panel
    home, derived from ``TILE_JOB_KINDS`` (Rule #5 — one data table,
    not a hand-special-cased branch per kind): the tile whose kinds
    tuple is EXACTLY ``(kind,)``, or None when no tile maps to it
    alone (``"chatgpt"``/``"gemini"`` share "website_gen" with each
    other, so neither resolves here — that pairing is a DIFFERENT
    kind of surface, `PainterGui`'s own ``_controls_box``, not a
    per-kind ``ToolSettingsPanel``). GUI rework Phase 15: this is what
    lets ``PainterGui._tool_panel_key`` translate the AI checker's
    JOB_ORDER slot ("aicheck") to its MENU_TILES id ("image_checker")
    — the one job kind whose tile id differs from its slot, the exact
    same shape `bg`/`crop`/`upscale`/`aspect` already have (tile id ==
    slot, so they resolve to themselves) — without a NEW per-kind
    branch anywhere a future standalone job kind might need one."""
    for tile_id, kinds in TILE_JOB_KINDS.items():
        if kinds == (kind,):
            return tile_id
    return None


# --- Tool temp / before-after / restore (owner 2026-07-19) -----------
#
# The four in-place tools back the ORIGINAL of every file up before they
# touch it, so a job's whole folder (or one image) can be RESTORED and a
# before/after viewer can show both. Backups live under a gitignored
# project-local temp root, one subdir per job slot; cleared on the
# panel's CLOSE, on app exit, and swept at startup.
JOBTEMP_DIRNAME = ".painter_tmp"  # PROJECT_ROOT-relative temp/backup root
# alpha below this counts as a "removed" (transparent) pixel for the BG
# metric — the same opacity notion as CROP_INK_ALPHA / CLEAN_EDGE_ALPHA.
JOBTEMP_REMOVED_ALPHA = 40

# GUI rework Phase 7 (owner decision 2026-07-21): the site-generation
# pipeline (BG -> Crop -> Aspect(force) -> Upscale, Phase 8) backs up an
# image's state before EVERY enabled step it runs, not just once — so a
# per-step restore viewer (Phase 9) can revert any single stage without
# losing the others. JobTemp namespaces those per-step backups under
# this reserved subdir name, which a real image's relative path is never
# expected to collide with, so a named-step backup can never be confused
# with the plain step=None backup the four standalone tools have always
# used (CRITICAL regression guard — see jobtemp.py), or with another
# step's own backup.
JOBTEMP_STEPS_SUBDIR = "__steps__"

# The ORDERING CONTRACT `JobTemp.steps_for(rel)` relies on. The pipeline
# itself runs BG -> Crop -> Aspect -> Upscale (Phase 8's reordered
# _compose_post_save), bookended by two backups that are not pipeline
# STEPS themselves: "original" is the pristine baseline captured before
# the pipeline touches the file at all — what "restore everything to
# pristine" restores to, via the explicit call
# `restore_to(rel, step="original")` — and "fixer" is the Fixer AI's
# pre-fix snapshot (Phase 20), taken long after the pipeline and the
# checker have already run. `steps_for()` filters THIS tuple down to
# whichever steps actually backed up one rel, so its result is always in
# this same original -> bg -> crop -> aspect -> upscale -> fixer order,
# regardless of the order the individual backup() calls actually
# happened in.
JOBTEMP_STEP_NAMES = ("original", "bg", "crop", "aspect", "upscale", "fixer")

# Intermediate-backup disk cap (owner decision 2026-07-21): 4 GiB per
# job. Findings' memory math — 4 enabled steps x ~3MB/image = ~12MB/image
# (~15MB with Fixer), so a realistic overnight batch (~300 images) peaks
# ~3.6-4.5GB, transient and cleared on close — sits close to this cap in
# the "keep every step" default case. `JobTemp.over_cap()` is a SIGNAL
# only (JobTemp never auto-evicts anything itself); the Phase 8 caller
# reads it to stop taking NEW per-step backups (falling back to
# original-only) and raise a persistent dashboard banner.
JOBTEMP_MAX_BYTES = 4 * 1024**3  # 4 GiB

# Per-agent "Keep every pipeline step (uses more disk)" toggle default
# (owner decision 2026-07-21) — ON: every enabled pipeline step gets its
# own restorable backup rather than only the original baseline. Consumed
# by the AgentPanel's ``keep_all_steps_var`` (GUI rework Phase 8);
# JobTemp itself has no notion of "agents" — it only ever backs up
# whatever step name a caller passes.
JOBTEMP_KEEP_ALL_STEPS_DEFAULT = True

# GUI rework Phase 8: the LOUD, PERSISTENT dashboard banner text a site
# job's panel shows the ONE time its JobTemp crosses JOBTEMP_MAX_BYTES
# (owner decision: "loud persistent dashboard banner, not just a log
# line") — formatted from that same constant so the number in the
# message can never drift from the real cap. Plain, static copy (no
# per-call parameters), so it lives here like every other user-facing
# string constant (SAFER_PREAMBLE, CONTINUE_NUDGE, AI_CHECK_INSTRUCTIONS).
JOBTEMP_CAP_BANNER_TEXT = (
    f"Backup cap reached ({JOBTEMP_MAX_BYTES / 1024 ** 3:.0f} GiB) — new"
    " per-step backups have stopped for this run; every image still"
    " keeps its ORIGINAL (pristine) backup, just not the BG/Crop/"
    "Aspect/Upscale in-between stages."
)

# GUI rework Phase 9: the per-step restore viewer's filmstrip label for
# each raw JOBTEMP_STEP_NAMES key ("original"/"bg"/... are internal
# identifiers, never shown to the owner as-is). The four real pipeline
# stages REUSE JOB_LABEL (Rule #5 — one label per tool kind, defined
# once); "original" and "fixer" are pipeline bookends with no tool of
# their own, so they get their own short label here. Every
# JOBTEMP_STEP_NAMES entry has one — see gui._filmstrip_stages.
JOBTEMP_STEP_LABEL = {
    "original": "Original",
    "bg": JOB_LABEL["bg"],
    "crop": JOB_LABEL["crop"],
    "aspect": JOB_LABEL["aspect"],
    "upscale": JOB_LABEL["upscale"],
    "fixer": "Fixer AI",
}

# The filmstrip's own final entry — the LIVE file as it stands right
# now. Not a JobTemp backup at all (so it carries no "Restore to here"
# of its own in gui.StepRestoreWindow), just the last stop after every
# kept named step in gui._filmstrip_stages's returned list.
STEP_RESTORE_CURRENT_LABEL = "Current"

# Transparency backdrop for the before/after viewer. BG removal (and the
# other tools) leave the AFTER image transparent where the background was
# cleared; drawn straight onto the panel colour, "removed" looks
# unchanged. So the viewer composites any image WITH ALPHA over a neutral
# light/dark checkerboard (the same cue Photoshop uses) and the removed
# area reads as removed. Deliberately theme-agnostic greys — this is a
# transparency backdrop, not app chrome.
CHECKER_TILE_PX = 12                 # checker square side, px
CHECKER_LIGHT = (205, 205, 205)      # the light squares
CHECKER_DARK = (150, 150, 150)       # the dark squares


# --- The Day/Night switch (image-based, ported from the owner's website
# switch — geometry scales from the switch height H) ------------------
# CRISP art (owner 2026-07-18): tkinter Canvas has no anti-aliasing, so
# the pill is composited from PIL images instead of raw ovals. The TRACK
# is the site's own pill SVG (assets/icons/switch_{night,day}.svg)
# rasterized through the icon SVG->PIL path; the SUN/MOON knobs are
# rendered anti-aliased with PIL (supersample Nx, then LANCZOS down).
SWITCH_H = 26               # mini switch height (px) for the top-right corner
SWITCH_ASPECT = 2.1539      # track width = round(H * this)
SWITCH_KNOB_FACTOR = 0.85   # knob diameter = round(H * this)
SWITCH_PAD_PX = 5           # canvas margin around the pill (hover + sun glow)
SWITCH_ANIM_MS = 600        # total knob-slide duration
SWITCH_FRAME_MS = 16        # ~60 fps -> ~37 smoothstep frames
SWITCH_HOVER_SCALE = 1.05   # knob grows this much on hover
# The theme CROSS-FADE (owner 2026-07-18): tkinter cannot interpolate
# widget colours, so a live theme flip repaints as an ugly cascade of
# half-themed frames (black boxes, half-styled spinners). The switch
# hides that cascade behind a STATIC SNAPSHOT of the OLD theme in a
# borderless overlay Toplevel, then fades the overlay's window alpha out
# over the freshly repainted NEW theme underneath.
SWITCH_FADE_MS = 500        # total snapshot cross-fade duration (alpha 1->0)
SWITCH_FADE_STEPS = 28      # alpha ramp ticks across SWITCH_FADE_MS (gentle ease-out)
SWITCH_SUPERSAMPLE = 4      # render knobs at Nx, then LANCZOS down for crisp edges
# During the fade a LARGE centred icon of the NEXT theme rides on the
# cover (SUN going to day, MOON going to night) and fades with it — the
# same PIL sun/moon renderers as the switch knob, sized to a fraction of
# the window's MIN dimension so the flip reads at a glance (owner
# 2026-07-19). The cover is forced painted BEFORE any theme repaint, so
# only the snapshot + icon are ever seen mid-flip, never the cascade.
SWITCH_COVER_ICON_FRAC = 0.30  # cover icon diameter = this * min(win W, H)
SWITCH_COVER_ICON_SS = 2       # supersample for the big cover icon (LANCZOS down)

# The SAME snapshot-cover machinery (gui.smooth_transition, owner
# 2026-07-20) also hides every DISCRETE relayout jump: the Controls
# collapse/expand, each agent's Settings-gear toggle, and a window
# maximize/restore. Those covers fade FASTER than the theme flip — a
# collapse should feel snappy, not ceremonial; the theme keeps its own
# SWITCH_FADE_* timing above.
TRANSITION_FADE_MS = 260    # collapse/settings/maximize cover fade
TRANSITION_FADE_STEPS = 14  # alpha ramp ticks across TRANSITION_FADE_MS

# --- Smooth window RESIZE (owner 2026-07-19) --------------------------
# customtkinter re-renders its canvas-drawn rounded widgets on every
# intermediate <Configure>, so dragging the window edge / maximizing used
# to run the ScrollFrame's expensive re-fit (scrollregion bbox scan +
# fill-height) per frame — visible jank. The ScrollFrame now DEBOUNCES
# that heavy pass: during an active resize it only tracks the canvas width
# (cheap) and re-arms a settle timer; the bbox/fill-height re-fit runs
# ONCE, this many ms after the LAST <Configure> ("wait for mouse release").
RESIZE_SETTLE_MS = 150

# the two track pill SVGs (stems, resolved in assets/icons) — reused
# straight from the owner's website switch, so the starfield / sky-clouds
# art matches the site exactly
SWITCH_TRACK_NIGHT_SVG = "switch_night"  # OFF track: dark #212736 starfield pill
SWITCH_TRACK_DAY_SVG = "switch_day"      # ON track: sky #5ea7ee + clouds pill

# both knobs are lit from this point (fraction of the knob box) so the
# radial gradient reads as a 3D sphere, not a flat disc
SWITCH_KNOB_HILIGHT = (0.40, 0.36)

# MOON knob (owner 2026-07-20 — "a real moon with craters"): a silver
# radial-gradient sphere with TERMINATOR shading (day side toward the
# light, the far limb falling into shadow), 7 craters of varied sizes
# each with a lit rim arc, and a subtle deterministic surface mottling.
SWITCH_MOON_CENTER = "#ececec"   # radial-gradient centre (bright silver)
SWITCH_MOON_EDGE = "#a8a8a8"     # radial-gradient edge (dim silver)
SWITCH_CRATER = "#8b93a1"        # crater floor (pre-shading; the
#                                  terminator darkens it on the far side)
SWITCH_CRATER_RIM = "#f6f6f2"    # the lit rim arc on each crater
SWITCH_CRATER_RIM_FRAC = 0.10    # rim stroke width = crater d * this
SWITCH_CRATER_RIM_ALPHA = 185    # rim arc opacity (alpha-BLENDED onto the
#                                  disc — a solid near-white arc read as a
#                                  pac-man ring, not a subtle lit rim)
SWITCH_CRATER_RIM_ARC_DEG = 140  # rim arc span, centred on the light side
# each crater: (diameter, centre-x, centre-y) as fractions of the knob
# diameter — 7 of varied sizes, spread so none overlap
SWITCH_CRATERS = (
    (0.28, 0.590, 0.300),
    (0.21, 0.300, 0.610),
    (0.14, 0.735, 0.590),
    (0.11, 0.420, 0.175),
    (0.09, 0.205, 0.360),
    (0.13, 0.565, 0.800),
    (0.08, 0.815, 0.415),
)
# TERMINATOR shading: sunlight falls from this 2D direction (x right,
# y down — negative = upper-left); brightness ramps from 1.0 on the lit
# limb down to SWITCH_MOON_DARK_FLOOR on the far limb, with the
# transition band SWITCH_MOON_TERMINATOR_SOFT of the diameter wide.
SWITCH_MOON_LIGHT_DIR = (-0.62, -0.44)
SWITCH_MOON_TERMINATOR_SOFT = 0.85  # soft band width (fraction of d)
SWITCH_MOON_DARK_FLOOR = 0.52       # far-limb brightness multiplier
# surface MOTTLING: a low-res value-noise grid smoothly upscaled over
# the disc, +- this many brightness steps; the seed is FIXED so the
# moon is identical every build (deterministic, owner 2026-07-20).
SWITCH_MOON_NOISE_SEED = 20260720
SWITCH_MOON_NOISE_CELLS = 9      # noise grid side (low res -> soft blobs)
SWITCH_MOON_NOISE_AMPL = 11.0    # +- brightness amplitude of the mottling
#                                  (6.0 measured invisible at cover size —
#                                  ~3% of the lit silver; 11 reads as faint
#                                  maria without getting dirty)

# SUN knob — gold radial gradient (bright centre -> amber edge) with a
# soft outer glow: a larger low-alpha gold disc behind, GaussianBlur-ed.
SWITCH_SUN_CENTER = "#ffd93d"    # radial-gradient centre (bright gold)
SWITCH_SUN_EDGE = "#e8940c"      # radial-gradient edge (amber)
SWITCH_SUN_GLOW = "#ffc832"      # the glow disc colour (blurred behind the sun)
SWITCH_SUN_GLOW_SCALE = 1.35     # glow disc diameter = knob d * this
SWITCH_SUN_GLOW_ALPHA = 140      # glow disc peak alpha (0-255) before blur
SWITCH_SUN_GLOW_BLUR = 0.14      # GaussianBlur radius = knob d * this
SWITCH_SUN_CELL_SCALE = 1.9      # knob image size = knob d * this (holds the glow)


# --- Prompt rules appended per site (owner 2026-07-17) ---------------

# The GUI shows ONE background dropdown PER SITE; the default
# selection is the site's default_background (ChatGPT transparent —
# it can do real alpha; Gemini white — the background fix clears it).
BACKGROUND_CHOICES = ("transparent", "white", "none")

_BACKGROUND_RULE = {
    "transparent": (
        "render on a fully TRANSPARENT background — a REAL alpha"
        " channel in the PNG, no backdrop of any kind; NEVER paint a"
        " fake gray-and-white checkerboard pattern as the background"
    ),
    "white": (
        "render on a PLAIN PURE WHITE background — flat white, no"
        " gradients, no vignette, no backdrop scenery"
    ),
    "none": None,
}

# Extra laws forced into EVERY prompt of a site. Gemini's weaker
# model drifts (wrong ratios, glossy reflections under the subject —
# the rondel_Dawn / rondel_Shield case), so it gets hard rules.
SITE_PROMPT_RULES = {
    "chatgpt": (),
    "gemini": (
        "absolutely NO reflections — no mirror effect, no glossy"
        " floor, no reflective surface under or around the subject",
    ),
}

# The aspect-ratio law DEPENDS ON THE IMAGE (owner 2026-07-17; since
# 2026-07-18 sent to BOTH sites — ChatGPT drifts too): most plates
# are badges/rondels/medallions -> a perfect square, but the
# church-window lancets are clearly taller than wide. The rule is
# picked from the PROMPT TEXT itself — first pattern that matches
# wins; the default is the square.
ASPECT_RULES = (
    (
        re.compile(r"\bTALL\b|\blancet\b", re.IGNORECASE),
        "ASPECT RATIO tall PORTRAIT — the image must be clearly"
        " TALLER than it is wide (around 2:3), matching the tall"
        " window shape described; never landscape, never square",
    ),
)
ASPECT_DEFAULT = (
    "ASPECT RATIO exactly 1:1 — a perfect square image"
)


def _aspect_rule(prompt_text: str) -> str:
    for pattern, rule in ASPECT_RULES:
        if pattern.search(prompt_text):
            return rule
    return ASPECT_DEFAULT


# --- Per-agent STYLE clause (owner 2026-07-19) -----------------------
#
# Each AgentPanel picks a rendering STYLE; the chosen clause is appended
# at the very END of that site's prompt suffix (AFTER the background rule
# and the Gemini laws), only when it is not "None". Pure data — the owner
# can reword the text here without touching any logic. "None" (the
# default) maps to an empty clause = nothing appended. STYLE_CHOICES
# preserves the dropdown order (None first).
STYLES = {
    "None": "",
    "Realistic": (
        "STYLE: photorealistic, high-fidelity finish - crisp fine detail,"
        " smooth clean surfaces, natural even lighting; NO film grain, NO"
        " speckle or noise, NO gritty sandpaper texture, NO heavy painterly"
        " stylization."
    ),
    "Oil painting": (
        "STYLE: classical oil painting - visible confident brushwork, rich"
        " layered color, subtle canvas texture, painterly light."
    ),
    "Watercolor": (
        "STYLE: soft watercolor - translucent layered washes, gentle color"
        " bleeds, visible paper grain, delicate edges."
    ),
    "3D render": (
        "STYLE: clean 3D render - physically based materials, soft studio"
        " lighting, smooth surfaces, subtle ambient occlusion, crisp"
        " reflections."
    ),
    "Flat vector": (
        "STYLE: flat vector illustration - bold clean shapes, solid fills,"
        " crisp edges, minimal or no gradients, no texture."
    ),
    "Ink engraving": (
        "STYLE: fine antique engraving - precise cross-hatched linework,"
        " high-contrast ink, old-print character."
    ),
}
STYLE_CHOICES = tuple(STYLES)  # dropdown order — "None" first
STYLE_DEFAULT = "None"


def prompt_suffix(
    site_key: str,
    background: str,
    prompt_text: str = "",
    style: str | None = None,
) -> str:
    """The rule block appended to one prompt of one site.

    ``style`` (a STYLES key, "None"/None = no style) appends that style's
    clause at the very END, after the aspect/background/site rules.
    """
    rules = [_aspect_rule(prompt_text)]
    bg_rule = _BACKGROUND_RULE[background]
    if bg_rule:
        rules.append(bg_rule)
    rules.extend(SITE_PROMPT_RULES[site_key])
    if len(rules) == 1:
        suffix = f"\n\nIMPORTANT: {rules[0]}."
    else:
        numbered = " ".join(
            f"{n}) {rule}." for n, rule in enumerate(rules, start=1)
        )
        suffix = f"\n\nIMPORTANT — follow ALL rules strictly: {numbered}"
    clause = STYLES.get(style) if style else None
    if clause:  # "None" -> "" -> falsy -> nothing appended
        suffix += f" {clause}"
    return suffix


# --- Safer-retry preamble (opt-in, owner 2026-07-17) -----------------

# When a SAFETY refusal is detected and "safer retry" is on, the same
# prompt is re-sent ONCE with this preamble prepended. It is an honest
# REFRAMING of legitimate allegorical art (no real people, symbolic,
# non-graphic) — not a way to force genuinely disallowed content. If
# it still refuses, the item is left REFUSED for the owner to rework.
SAFER_PREAMBLE = (
    "This is a purely SYMBOLIC stained-glass ALLEGORY of an abstract"
    " idea for a decorative church-window art set. There are NO real"
    " or identifiable people, no realism and nothing graphic — only"
    " simplified emblematic figures rendered as coloured glass and"
    " lead. Depict the CONCEPT itself (an emotion, virtue or vice),"
    " never a literal act; keep every element tasteful, non-violent"
    " and non-graphic. Treat any strong phrase below as a gentle"
    " metaphor, not a literal instruction.\n\n"
)


# --- Continue nudge (opt-in, ON by default, owner 2026-07-20) --------

# ChatGPT sometimes STALLS mid-image: the done edge fires (stop button
# gone) yet no image loads and the answer text is EMPTY — a NoImage /
# unknown-DOM state that matches no refusal/quota marker. The owner's
# fix is a plain "continue" nudge in the SAME chat, which usually makes
# it finish the pending image. On a NoImage the runner sends this ONCE
# (the prompt is already in the chat — we only tell it to continue),
# then either uses the recovered image or gives up loudly. Data only —
# the owner can reword it here.
CONTINUE_NUDGE = "Continue - please finish generating the image."


# --- AI features: free Gemini API (owner 2026-07-20) ------------------
#
# painter/ai.py drives the FREE AI Studio REST API (no SDK) for two GUI
# features: the sheet GENERATOR (text model) and the image CHECKER
# (vision model). Model names ROTATE with Google's releases — they are
# DATA here so the owner can bump them without touching code. The key
# lives in settings.json (gitignored) under GEMINI_KEY_SETTING; the GUI
# wizard writes it there and painter.ai reads it per call.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# The stable "-latest" aliases: Google keeps them pointed at a current
# free-tier flash model, so they don't 404 ("no longer available to new
# users") or 429 (free_tier limit 0) the way the pinned 2.0/2.5 names did
# for fresh keys. Verified 200 OK against a new AI Studio key 2026-07-21.
GEMINI_TEXT_MODEL = "gemini-flash-latest"    # sheet generator (free tier)
GEMINI_VISION_MODEL = "gemini-flash-latest"  # image checker (multimodal, reads images)
# GUI rework Phase 18 (API Image Generation): the image-generation/edit
# model, separate from the free TEXT/VISION models above. PAID-ONLY on
# the owner's key TODAY — every free-tier quota for this model is 0
# (verified live against a real captured 429, 2026-07-21; see
# AI_IMAGE_QUOTA_MARKERS below and ai.PaidFeatureRequired), so a call
# raises loudly until the owner enables billing on the AI Studio
# project. Google is retiring THIS generation in October 2026 in
# favour of "Nano Banana 2" (gemini-3.1-flash-image) — bump this
# string when that lands; nothing else in the code names the model.
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
GEMINI_KEY_SETTING = "gemini_api_key"     # the settings.json key name
# where the wizard's step-1 button sends the browser (the key page)
AI_STUDIO_URL = "https://aistudio.google.com/apikey"
# free-tier pacing: the flash free tier allows ~10 requests/minute, so
# consecutive calls keep at least this many seconds apart (6.0 would sit
# exactly on the limit; 6.5 leaves headroom for clock skew)
AI_CALL_PAUSE_S = 6.5
AI_TIMEOUT_S = 120.0  # one HTTP call's hard cap (vision calls are slow)
# the wizard's "Test key" prompt — tiny and cheap, the answer is shown
AI_TEST_PROMPT = "Reply with exactly: OK"
# TRANSIENT API failures RETRY (the free tier 503s under load, 429s at
# the rate cap); PERMANENT ones (400 bad request, 401/403 bad key, 404
# no such model) raise on the first try. The client keys the retry on
# the HTTP status.
AI_TRANSIENT_STATUS = frozenset({429, 500, 503})
AI_RETRY_MAX = 3        # total attempts per call before giving up loudly
AI_RETRY_BACKOFF_S = 5.0  # fixed wait before a 503/500 retry
# a 429 carries the server's own backoff (error.details[].retryDelay /
# "please retry in Xs"); honour it, but never wait longer than this
AI_RETRY_MAX_WAIT_S = 30.0

# GUI rework Phase 18: the free-tier-EXHAUSTED signal that makes a 429
# PERMANENT (ai.PaidFeatureRequired) instead of transient. Each inner
# tuple is an AND-group — every substring in it must appear
# (case-insensitive) in the 429 message for that group to fire; the
# whole marker fires when ANY group matches (OR across groups).
# Captured VERBATIM from the owner's key against GEMINI_IMAGE_MODEL,
# 2026-07-21 (the exact body lives in ai.md / test_ai.py's fixture):
#   "You exceeded your current quota, please check your plan and
#   billing details. ... Quota exceeded for metric: ...
#   generate_content_free_tier_input_token_count, limit: 0, model:
#   ... Quota exceeded for metric: ...generate_content_free_tier_
#   requests, limit: 0, model: ... Please retry in 15.776751513s."
# TRAP (do not "fix" this): that body ALSO names a "retry in Xs" hint,
# same as an ordinary transient rate-limit 429 — classification keys
# on THESE substrings only, never the retry hint. A 429 matching
# NEITHER group is ambiguous and stays TRANSIENT (retries as today) —
# retrying a permanent error wastes a few calls, but giving up on a
# genuinely transient one is worse (owner decision).
AI_IMAGE_QUOTA_MARKERS = (
    ("free_tier", "limit: 0"),
    ("check your plan and billing details",),
)

# --- the AI sheet generator (owner's #2: follow-up questions) ---------
AI_MAX_QUESTIONS = 6  # the clarifying poll is capped at this many
# where AI-generated sheets are saved (owner content, NOT gitignored —
# but never committed by an agent either; the dir is created on demand)
SHEETS_DIR = PROJECT_ROOT / "sheets"
# FIRST call system prompt: the contract + "questions only". {contract}
# is instructions.md verbatim; {max_q} is AI_MAX_QUESTIONS.
AI_QUESTIONS_SYSTEM = (
    "You help an operator author a PromptPainter prompt-sheet (.md"
    " file). This is the sheet contract you must know:\n\n{contract}\n\n"
    "DO NOT produce the sheet yet. First return ONLY a short numbered"
    " list of clarifying questions (at most {max_q}), one question per"
    " line, no other text before or after. Ask only what the request"
    " leaves unknown of: theme and visual style, image count, the drop"
    " folder (assets/<category>/<rest>), file naming, background"
    " (transparent / white), shape (rondel / lancet / plate), any"
    " special laws."
)
# SECOND call system prompt: the contract + "the raw .md only".
AI_SHEET_SYSTEM = (
    "You author a PromptPainter prompt-sheet (.md file). Follow the"
    " sheet contract EXACTLY:\n\n{contract}\n\n"
    "Return ONLY the raw markdown of the complete sheet — no"
    " commentary, no surrounding code fence around the whole file. It"
    " must carry exactly one '# H1' theme line and, per image, a"
    " '**Title** → `assets/<category>/<rest>/<File>.png`' line followed"
    " by one fenced prompt block."
)
# SECOND call user content: the request + the answered poll.
AI_SHEET_REQUEST = (
    "The operator's request:\n{request}\n\n"
    "The operator answered the clarifying questions:\n{qa}\n\n"
    "Write the complete sheet now."
)
# ONE automatic repair round when the parser rejects the produced md.
AI_REPAIR_PROMPT = (
    "The sheet you produced fails the PromptPainter parser with these"
    " problems:\n{problems}\n\nHere is the sheet you produced:\n\n{md}"
    "\n\nReturn the corrected COMPLETE .md (raw markdown, no"
    " commentary, no code fence around the whole file), fixing every"
    " listed problem and keeping everything else identical."
)

# --- the AI image checker (owner's #3: banal defects only) ------------
AI_FLAGS_FILENAME = "ai_flags.json"  # under <out>/_state/
# the vision instruction — BANAL defects only, in a strict short format
# the parser (painter.ai.parse_check_response) can read
AI_CHECK_INSTRUCTIONS = (
    "You are a strict quality checker of AI-generated decorative images"
    " (badges, rondels, stained-glass panels, emblems, plates). Look"
    " ONLY for these BANAL defects: the subject or its circle/frame"
    " slightly CUT OFF at an image edge; leftover background patches or"
    " halos around the subject; stray lines, smudges or floating"
    " artifacts; watermark or text artifacts; an obviously clipped or"
    " asymmetric frame. IGNORE style, beauty and artistic choices —"
    " they are not defects.\n"
    "Respond in EXACTLY this format: if the image is clean, reply with"
    " the single line 'OK'. Otherwise reply with the first line"
    " 'DEFECTS:' followed by one short defect description per line,"
    " each line starting with '- '."
)
# the per-item extra suffix appended when a flagged image is re-sent to
# its original generator ({defects} = the '; '-joined defect list)
AI_FIX_NOTE = (
    "The previous attempt had these flaws: {defects}. Regenerate the"
    " same image correcting them."
)


# --- Timing ----------------------------------------------------------

@dataclass(frozen=True)
class Timing:
    """All waits and paces, in seconds."""

    # human-like hesitation between UI actions (click box -> paste,
    # paste -> send ...): a random delay drawn from this range, like
    # a person doing Ctrl+V and then Enter
    action_delay_min_s: float = 0.2
    action_delay_max_s: float = 0.6
    # a required element (prompt box, send button) must appear;
    # SPAs morph elements a beat after input events, so lookups
    # poll instead of failing on a one-shot snapshot
    selector_timeout_s: float = 10.0
    # submit clicked -> the busy signal (stop button) must appear
    busy_appear_timeout_s: float = 30.0
    # no busy signal after this long -> click send / press Enter again
    # (the send button is sometimes momentarily blocked)
    send_retry_after_s: float = 5.0
    # busy signal seen -> its disappearance (the done edge), hard cap
    generation_timeout_s: float = 420.0
    # done edge -> a real (non-placeholder) result <img> src
    image_ready_timeout_s: float = 90.0
    # DOM polling step
    poll_interval_s: float = 0.5
    # "still generating..." log cadence during long waits
    progress_log_interval_s: float = 15.0
    # polite pause between prompts (image quotas are real): a RANDOM
    # duration drawn uniformly from [min, max], fractional seconds
    # included (e.g. 12.56s) — less robotic pacing
    pause_min_s: float = 30.0
    pause_max_s: float = 75.0


TIMING = Timing()

# The GUI's Pause toggle (owner 2026-07-21) blocks the run loop (and the
# tool/AI-check worker loops) between items until Resume or Stop — the
# poll granularity of that wait. A plain top-level constant, not a
# Timing field: it is an internal wait-loop step, never a per-run/
# per-site tunable exposed in the UI (unlike Timing.pause_min_s/max_s,
# the random PACING wait between prompts — a different, existing
# feature that shares the word "pause" but not the mechanism).
PAUSE_POLL_INTERVAL_S = 0.5

# An <img> narrower than this is a placeholder, not a generated image.
MIN_IMAGE_PX = 64


# --- Quota reset time (owner's #2) -----------------------------------

# ChatGPT's live quota message names the wait ("... when the limit
# resets in 27 minutes" / "in 14 hours"); Serbian-locale variants
# phrase it as "za 27 minuta" / "za 14 sati". Each pattern captures
# ONE number; the value is multiplied by the unit's seconds. Matches
# are summed so "in 2 hours" + a minutes phrase both count; an
# unparseable message yields None (the caller still stops — the
# reset time is a bonus, never a requirement).
QUOTA_RESET_PATTERNS: tuple[tuple[re.Pattern, float], ...] = (
    (re.compile(r"\bin\s+(\d+)\s*h(?:ours?|rs?)?\b", re.IGNORECASE), 3600.0),
    (re.compile(r"\bin\s+(\d+)\s*min(?:ute)?s?\b", re.IGNORECASE), 60.0),
    # Serbian: "za 14 sati" / "za 2 sata" / "za 27 minuta" / "za 1 minut"
    (re.compile(r"\bza\s+(\d+)\s*sat(?:i|a)?\b", re.IGNORECASE), 3600.0),
    (re.compile(r"\bza\s+(\d+)\s*min(?:ut)?a?\b", re.IGNORECASE), 60.0),
)


def parse_quota_reset(text: str) -> float | None:
    """Seconds until the quota resets, read from a quota response.

    None when no pattern matches — the message carried no parseable
    wait time (e.g. Gemini's "as soon as your limit resets").
    """
    total = 0.0
    found = False
    for pattern, unit_s in QUOTA_RESET_PATTERNS:
        match = pattern.search(text)
        if match:
            total += float(match.group(1)) * unit_s
            found = True
    return total if found else None


# --- Site DOM states (ONE config block, with fallbacks) --------------

@dataclass(frozen=True)
class SiteConfig:
    """The DOM hooks the driver watches on one site."""

    name: str
    # the tab the launcher opens
    url: str
    # substring of the tab URL used to find the already-open tab
    url_fragment: str
    # the BACKGROUND_SUFFIXES key used when the mode is 'auto'
    default_background: str
    # the contenteditable prompt box
    prompt_box: tuple[str, ...]
    # the idle send button
    send_button: tuple[str, ...]
    # visible only WHILE generating; its disappearance is the done edge
    busy_signal: tuple[str, ...]
    # one response turn; the LAST match holds the result
    response_container: tuple[str, ...]
    # generated <img> nodes inside the last response container
    result_image: tuple[str, ...]
    # substrings marking a SAFETY refusal of ONE prompt — the item
    # is reported and skipped, the run continues (owner 2026-07-17)
    refusal_text_markers: tuple[str, ...]
    # substrings marking a quota/rate limit — TERMINAL for the whole
    # site: report and stop, never blind-retry
    quota_text_markers: tuple[str, ...]
    # the sidebar "New chat" control (owner captures 2026-07-18) —
    # clicked between collections/folders when the option is on
    new_chat: tuple[str, ...] = ()
    # GUI rework Phase 17 (WEBSITE FIX, HIGH RISK / owner-dependent):
    # the attach/upload control that opens this site's file picker in
    # the chat composer, and the (often hidden-by-design) <input
    # type="file"> it drives. EMPTY BY DEFAULT = WEBSITE FIX DISABLED
    # for this site — SiteDriver.submit_fix raises FixNotConfigured
    # immediately instead of guessing. DO NOT INVENT THESE SELECTORS.
    #
    # OWNER: to enable WEBSITE FIX for a site, open its chat in the
    # automation Chrome profile, inspect the "+"/attach button and the
    # file input it drives (DevTools -> Elements — same method used to
    # capture every other selector in this file), and paste them here
    # as tuples of fallback CSS selectors, e.g.:
    #   attach_button=('button[aria-label="Attach files"]',),
    #   file_input=('input[type="file"]',),
    attach_button: tuple[str, ...] = ()
    file_input: tuple[str, ...] = ()


SITES = {
    "chatgpt": SiteConfig(
        name="ChatGPT",
        url="https://chatgpt.com/",
        url_fragment="chatgpt.com",
        default_background="transparent",
        # Verified against the live DOM by the owner, 2026-07-17
        # (UV/ screenshots): the composer button keeps the stable id
        # #composer-submit-button and morphs by state — empty box =
        # "Start Voice", text = data-testid="send-button" /
        # aria-label="Send prompt", GENERATING = data-testid=
        # "stop-button" / aria-label="Stop answering". A response
        # turn is <section data-turn="assistant" data-testid=
        # "conversation-turn-N">; the generated image sits in
        # <div id="image-<uuid>" class="group/imagegen-image"> as
        # <img alt="Generated image: ..." src="https://chatgpt.com/
        # backend-api/estuary/content?id=...&sig=...">.
        prompt_box=(
            "#prompt-textarea",
            "div.ProseMirror[contenteditable='true']",
        ),
        send_button=(
            'button[data-testid="send-button"]',
            "#composer-submit-button",
            'button[aria-label*="Send" i]',
        ),
        busy_signal=(
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop answering" i]',
        ),
        response_container=(
            'section[data-turn="assistant"]',
            '[data-testid^="conversation-turn"][data-turn="assistant"]',
            'article[data-testid^="conversation-turn"]',
            "article",
        ),
        result_image=(
            'div[id^="image-"] img',
            'img[alt*="Generated image" i]',
            'img[src*="/backend-api/"]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_text_markers=(
            "can't create",
            "cannot create",
            "can't generate",
            "cannot generate",
            # live capture 2026-07-17: "We're so sorry, but the prompt
            # may violate our content policies. If you think we got it
            # wrong, please retry or edit your prompt." — "content
            # polic" catches both policy and policies
            "content polic",
            "may violate",
            "violate our",
            "retry or edit your prompt",
            "unable to create",
            "not able to create",
        ),
        quota_text_markers=(
            "reached your limit",
            "too many requests",
            "rate limit",
            "try again later",
            # live capture 2026-07-17: "You've hit the Plus plan limit
            # for image generations requests. You can create more images
            # when the limit resets in 14 hours ..."
            "plan limit",
            "limit resets",
            "generation limit",
            "image generation limit",
        ),
        new_chat=(
            'a[data-testid="create-new-chat-button"]',
            'a[href="/"][data-sidebar-item="true"]',
        ),
        # WEBSITE FIX (GUI rework Phase 17) — DISABLED for ChatGPT
        # until the OWNER pastes real selectors here (see SiteConfig's
        # field comment above for exactly what to capture and how).
        attach_button=(),
        file_input=(),
    ),
    "gemini": SiteConfig(
        name="Gemini",
        url="https://gemini.google.com/app",
        url_fragment="gemini.google.com",
        default_background="white",
        # Verified against the live DOM by the owner, 2026-07-17
        # (UV/Gemini screenshots): the prompt box is <rich-textarea>
        # holding div.ql-editor[contenteditable] ("Ask Gemini");
        # send and stop share ONE container, <div data-test-id=
        # "send-button-container"> > <gem-icon-button> — typing makes
        # it visible as aria-label="Send message", generating turns
        # it into class "stop" / aria-label="Stop response" with
        # mat-icon "stop". A response is <model-response>; the image
        # sits under generated-image > single-image >
        # button.image-button as <img class="image animate loaded"
        # alt=", AI generated" src="blob:https://gemini.google.com/...">.
        prompt_box=(
            "rich-textarea div.ql-editor[contenteditable='true']",
            "rich-textarea div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
        ),
        send_button=(
            'div[data-test-id="send-button-container"] button',
            'button[aria-label*="Send message" i]',
            'button[aria-label*="Send" i]',
        ),
        busy_signal=(
            'button[aria-label*="Stop response" i]',
            "gem-icon-button.stop button",
            'button[aria-label*="Stop" i]',
            'mat-icon[data-mat-icon-name="stop"]',
        ),
        response_container=(
            "model-response",
            "message-content",
        ),
        result_image=(
            "generated-image img",
            "single-image img",
            "button.image-button img",
            'img[alt*="AI generated" i]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_text_markers=(
            "can't create",
            "cannot create",
            "can't generate",
            "cannot generate",
            "unable to generate",
            "unsafe",
            # Gemini answers in the account's language — Serbian too
            "ne mogu da generi",
            "ne mogu da kreiram",
            "bezbednosn",
        ),
        quota_text_markers=(
            "quota",
            "limit reached",
            "too many requests",
            "rate limit",
            "try again later",
            # live capture 2026-07-17: "I can create more images as
            # soon as your limit resets. Check your usage in Settings."
            "limit resets",
            "your limit",
            "check your usage",
            "dostigli ste",
            "ograničenj",
        ),
        new_chat=(
            'a[aria-label="New chat"]',
            'gem-icon-button a[href="/app"]',
        ),
        # WEBSITE FIX (GUI rework Phase 17) — DISABLED for Gemini
        # until the OWNER pastes real selectors here (see SiteConfig's
        # field comment above for exactly what to capture and how).
        attach_button=(),
        file_input=(),
    ),
}

# When to open a fresh chat during a run (GUI dropdown / CLI flag):
# off = one long conversation per site; collection = a new chat after
# every finished collection; folder = also between folder groups
# INSIDE a collection (primary -> colored ...).
NEW_CHAT_CHOICES = ("off", "collection", "folder")
