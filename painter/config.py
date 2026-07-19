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
PROGRESS_SUFFIX = ".progress.json"
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
UPSCALE_MODEL = "realesrgan-x4plus"
# Gating (owner 2026-07-19: now FOUR editable params, defaults reproduce
# the old locked 2026-07-18 rule). An image qualifies ONLY if its aspect
# ratio W/H is within [UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX] (the
# circular/badge class) AND (W < UPSCALE_MIN_WIDTH OR H <
# UPSCALE_MIN_HEIGHT); then it is upscaled (native 4x + LANCZOS, aspect
# preserved) so W >= UPSCALE_MIN_WIDTH and H >= UPSCALE_MIN_HEIGHT. The
# defaults (800 / 800 / 0.9 / 1.1) are the old min_px=800 + aspect_tol=0.1
# behaviour. The GUI exposes all four PER AGENT and in the standalone
# Upscale dialog (both persisted); these are just the shipped defaults.
UPSCALE_MIN_WIDTH = 800
UPSCALE_MIN_HEIGHT = 800
UPSCALE_ASPECT_MIN = 0.9
UPSCALE_ASPECT_MAX = 1.1
# GUI spinner steps for the four upscale-gate fields (Rule #4).
UPSCALE_MINDIM_STEP = 50    # min W / min H spinner step (px)
UPSCALE_ASPECT_STEP = 0.05  # aspect from / to spinner step
UPSCALE_ASPECT_DECIMALS = 2  # aspect fields show 2 decimals (0.90 / 1.10)


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
JOB_ORDER = ("chatgpt", "gemini", "bg", "crop", "upscale", "aspect")
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
}

# the aggregate metric each TOOL panel reports (its per-image % means):
#   bg = removed pixels, crop = area reduction, upscale = area increase,
#   aspect = deformation (growth of the stretched axis). measure() tags
#   every item with the same word so the panel header and the rows agree.
JOB_METRIC = {
    "bg": "removed",
    "crop": "reduction",
    "upscale": "increase",
    "aspect": "deformation",
}


def job_color_pair(kind: str) -> tuple[str, str]:
    """The (day, night) colour pair for one job kind — a CTk light/dark
    tuple that auto-flips on set_appearance_mode()."""
    return JOB_COLORS[kind]


# how many grid COLUMNS for N active panels; rows = ceil(N / cols). The
# owner's chosen shape: 1→1, 2→2, 3→3, 4→2x2, 5→2x3 (ChatGPT+Gemini in
# the top row, 6th cell empty), 6→2x3.
GRID_COLS_BY_COUNT = {1: 1, 2: 2, 3: 3, 4: 2, 5: 2, 6: 2}

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

# the two track pill SVGs (stems, resolved in assets/icons) — reused
# straight from the owner's website switch, so the starfield / sky-clouds
# art matches the site exactly
SWITCH_TRACK_NIGHT_SVG = "switch_night"  # OFF track: dark #212736 starfield pill
SWITCH_TRACK_DAY_SVG = "switch_day"      # ON track: sky #5ea7ee + clouds pill

# both knobs are lit from this point (fraction of the knob box) so the
# radial gradient reads as a 3D sphere, not a flat disc
SWITCH_KNOB_HILIGHT = (0.40, 0.36)

# MOON knob — silver radial gradient (bright centre -> dim edge) + 3
# darker craters; the offset highlight gives the subtle inner shading.
SWITCH_MOON_CENTER = "#e8e8e8"   # radial-gradient centre (bright silver)
SWITCH_MOON_EDGE = "#a0a0a0"     # radial-gradient edge (dim silver)
SWITCH_CRATER = "#6a7280"        # the 3 craters
# each crater: (diameter, centre-x, centre-y) as fractions of the knob
# diameter, converted from the spec's edge insets
SWITCH_CRATERS = (
    (0.31, 0.595, 0.305),
    (0.25, 0.305, 0.625),
    (0.16, 0.740, 0.610),
)

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


def prompt_suffix(site_key: str, background: str, prompt_text: str = "") -> str:
    """The rule block appended to one prompt of one site."""
    rules = [_aspect_rule(prompt_text)]
    bg_rule = _BACKGROUND_RULE[background]
    if bg_rule:
        rules.append(bg_rule)
    rules.extend(SITE_PROMPT_RULES[site_key])
    if not rules:
        return ""
    if len(rules) == 1:
        return f"\n\nIMPORTANT: {rules[0]}."
    numbered = " ".join(
        f"{n}) {rule}." for n, rule in enumerate(rules, start=1)
    )
    return f"\n\nIMPORTANT — follow ALL rules strictly: {numbered}"


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
    ),
}

# When to open a fresh chat during a run (GUI dropdown / CLI flag):
# off = one long conversation per site; collection = a new chat after
# every finished collection; folder = also between folder groups
# INSIDE a collection (primary -> colored ...).
NEW_CHAT_CHOICES = ("off", "collection", "folder")
