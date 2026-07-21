"""Dashboard per-JOB panels, status badges, and the Main Menu tiles
(owner 2026-07-19 / 2026-07-20 / GUI rework Phase 10).
"""

from dataclasses import dataclass

# --- Dashboard per-JOB panels (owner 2026-07-19) ---------------------
#
# The dashboard shows one panel PER RUNNING JOB (up to 7 in parallel):
# the two image-generation SITES, the API IMAGE GEN job (GUI rework
# Phase 19 — same "generation" tier, driven through the paid REST API
# instead of a browser tab), plus the four in-place TOOLS, each its
# own worker thread and its own panel. A panel appears when its job
# starts and gets a CLOSE button when it finishes; the grid re-flows by
# how many are active. JOB_ORDER is the FIXED priority (gen first) that
# places panels row-major into the grid, so ChatGPT + Gemini always take
# the top cells. All of this is PURE data (strings/numbers only) so the
# engine and tests import config.py without tkinter.
JOB_ORDER = (
    "chatgpt", "gemini", "api_image", "bg", "crop", "upscale", "aspect",
    "aicheck",
)
JOB_TOOL_KINDS = ("bg", "crop", "upscale", "aspect")

# button + panel-header label per job (the three tool buttons drop the
# old "only…" wording, owner 2026-07-19)
JOB_LABEL = {
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
    "api_image": "API Image GEN",
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
# "api_image" reuses the Gemini logo (GUI rework Phase 19) — the paid
# image model IS Gemini, just driven through its REST API, same as
# MENU_TILES's own api_image_gen tile already picked.
JOB_LOGO = {
    "chatgpt": "chatGPT",
    "gemini": "gemini",
    "api_image": "gemini",
    "bg": "bg",
    "crop": "crop",
    "upscale": "upscale",
    "aspect": "aspect",
    "aicheck": "ai",
}

# per-job (day, night) colour pair — the header name + the tool button
# fill. CTk stores the tuple and re-resolves it per appearance mode, so
# a Day/Night flip recolours them with no re-walk. "api_image" reuses
# the SAME orange accent MENU_TILES's api_image_gen tile already picked
# (see MENU_TILES below, which now reads it back from here — Rule #5,
# ONE hue, not two literals that could drift apart).
JOB_COLORS = {
    "chatgpt": ("#1a8f6a", "#00bc8c"),  # green
    "gemini": ("#2f6fb0", "#4a9eff"),   # blue
    "api_image": ("#c2410c", "#fb923c"),  # orange
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
# 8 (GUI rework Phase 19 adds "api_image" to JOB_ORDER, the new max
# active count) stays 3x3 too — one more empty cell, the same shape the
# owner already accepted at 7.
GRID_COLS_BY_COUNT = {1: 1, 2: 2, 3: 3, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3}


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
    # GUI rework Phase 19: wired up — the adapter/panel/gating below.
    # Reads its accent back from JOB_COLORS (this job kind's own entry,
    # added this phase) instead of a second hardcoded tuple (Rule #5).
    MenuTile(
        id="api_image_gen", label="API Image GEN",
        description="Generate images via the paid Gemini API",
        icon=JOB_LOGO["api_image"], color=JOB_COLORS["api_image"],
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
# kinds (it lights up while EITHER site runs); "ai_sheet_gen" has no
# dashboard job of its own (it only ever launches a dialog), hence the
# empty tuple. "api_image_gen" (GUI rework Phase 19) now DOES have one
# — a single-kind tile like bg/crop/upscale/aspect, resolved back by
# ``tile_for_kind`` the same way.
TILE_JOB_KINDS: dict[str, tuple[str, ...]] = {
    "website_gen": ("chatgpt", "gemini"),
    "ai_sheet_gen": (),
    "api_image_gen": ("api_image",),
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
