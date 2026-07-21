"""Change aspect ratio (owner's batch deform tool, 2026-07-19) and the
shared stackable filter framework (owner decision 2026-07-21).

painter/aspect.py DEFORMS every image in a folder to a target ratio
X:Y in place — a non-proportional LANCZOS STRETCH (intended). The
rule NEVER shrinks either dimension: the result is the smallest box
of the target ratio that still CONTAINS the original, so exactly ONE
axis grows and neither is cut. An image whose current W/H is within
ASPECT_TOL of the target ratio is already at ratio and left BYTE-
UNCHANGED (no write). The GUI's ratio prompt defaults to 16:9.
"""

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
# building the FilterCondition; `matches()` itself is unchanged — this
# only affects what the widget WRITES into a condition's lo/hi for this
# one kind.
FILTER_ASPECT_EXACT_TOL = 0.02
