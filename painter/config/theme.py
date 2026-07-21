"""GUI themes: the single source of truth (owner 2026-07-18).

TWO coordinated palettes flipped as one by the GUI's Day/Night
switch. This block is PURE DATA (hex strings only) so the engine and
every test can import config.py without pulling in tkinter /
ttkbootstrap. gui.py turns each entry into the two backbones:
  - `ttk`   -> the 16 ttkbootstrap colour keys. "night" is the
              built-in darkly theme written out VERBATIM (the owner
              is happy with it); "day" is a custom light theme
              ("painter_day") mapped from the owner's website LIGHT
              palette, authored to how THIS app actually uses each
              key. Two keys are deliberately repurposed: `dark` is a
              LIGHT surface on day (#e8e4dd) because the app uses it
              only as the combobox-dropdown / hover / code-box
              background, and `light` is a MID grey (#888888) because
              the app uses it only as a muted-text / outline
              foreground, never as a light fill.
  - `status`-> the semantic colours that are set PER WIDGET at
              construction (Select-tree leaf rows, DocWindow text
              tags) and so must be recomputed on a flip; contrast-
              tuned for each background.
  - `ttkname`/`mode`/`switch_on` -> the ttkbootstrap theme name, the
              customtkinter appearance mode, and the switch knob side
              (False = left/moon, True = right/sun).
"""

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
# 2026-07-20) also hides every DISCRETE Tk-level relayout jump: the
# Controls collapse/expand, each agent's Settings-gear toggle, and each
# tool panel's Advanced-section toggle. Those covers fade FASTER than
# the theme flip — a collapse should feel snappy, not ceremonial; the
# theme keeps its own SWITCH_FADE_* timing above. NOT used for a window
# maximize/restore (owner 2026-07-21 perf fix — covering that OS-level
# state jump broke it; see gui/app_build.py's _on_root_configure).
TRANSITION_FADE_MS = 260    # collapse/settings cover fade
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

# --- ScrollFrame fill_height re-fit (owner 2026-07-21 workflow fix; made
# event-driven 2026-07-21 perf fix) -------------------------------------
# The fill_height re-fit above re-triggers from an ACTUAL canvas resize
# (a real window resize/maximize) or an explicit refresh() call — once
# _apply_fill_height has ever forced the embedded body's height via
# canvas itemconfigure, body's OWN <Configure> stops firing in response
# to its nested content simply growing (a canvas "window" item's forced
# dimension is now externally pinned, decoupled from the child's natural
# pack-driven size request), so a content-height change from a widget
# with no reference to the ScrollFrame (e.g. an AgentPanel's Settings-
# gear reveal, or a ToolSettingsPanel's Advanced-section reveal) would
# otherwise leave the scrollregion stuck too short, with the real bottom
# of the content unreachable on a short window. THIS USED TO BE self-
# healed by a perpetual after() poll re-checking the fit forever, even
# fully idle — the owner reported the constant background timer as
# visible scroll jank ("renders so badly it's horrible"). Replaced with
# an explicit ``on_layout_change`` callback each such panel calls right
# after its own reveal (wired by PainterGui to ``ScrollFrame.refresh``)
# — zero timers, zero idle cost.

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
