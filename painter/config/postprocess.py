"""Postprocess: background removal + crop (owner workflow step 6).

painter/postprocess.py runs over every saved image; the two steps
are COMPOSABLE (owner's #7): remove_background auto-detects per
file (already-transparent -> nothing, white/black cleared,
ambiguous -> unclear, left untouched); crop_transparent autocrops
a transparent image to its content bounding box.
"""

# ═══════════════════════════ PNG WRITE SETTINGS ════════════════════════
# HOW every pipeline step writes its PNG back (owner 2026-08-07, the
# "why does BG removal take 10 s on one image" measurement). The whole
# removal ALGORITHM on a 1664x2550 plate — decode, colour distance,
# connected-component flood, alpha ramp — costs 0.3 s; the save cost 9.5 s,
# because Pillow's `optimize=True` re-tries every PNG scanline filter for
# a 4.6 % smaller file (4.32 MB vs 4.52 MB). That trade is nonsense for an
# asset the owner copies into DOMY: zlib level 6 keeps ~95 % of the size
# win at 1/7 the time, turning a 10 s image into ~1.7 s.
#
# PNG_SAVE_KWARGS is THE one authority — every `Image.save(..., "PNG")`
# in the pipeline (bg_remove, postprocess crop, aspect, upscale) splats it
# and no module passes its own compression arguments.
PNG_COMPRESS_LEVEL = 6  # zlib level 0-9; 6 = Pillow's default, 9 ~= optimize
PNG_SAVE_KWARGS = {"compress_level": PNG_COMPRESS_LEVEL}

# ═══════════════════════════ CROP THRESHOLDS ═══════════════════════════
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

# ═══════════════════════════ EDGE-HALO CLEANUP ═════════════════════════
# CONSERVATIVE EDGE-HALO CLEANUP (owner 2026-07-18). Before cropping,
# faint pixels (alpha < CLEAN_EDGE_ALPHA) that are CONNECTED TO THE IMAGE
# BORDER — the visible stray line / halo in the transparent frame — have
# their alpha zeroed. Interior soft edges are enclosed by the solid
# subject, never border-connected, and stay untouched. This is NOT a
# global alpha[alpha<K]=0 (that would nibble genuine soft edges).
CLEAN_EDGE_ALPHA = 40     # faint pixels below this may be border halo
CLEAN_EDGE_ENABLE = True  # run the border-connected cleanup before crop

# ═════════════════ BLACK-VOID REMOVAL + SAFETY GUARD ═══════════════════
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

# ═══════════════════════════ BACKGROUND MODE ═══════════════════════════
# BACKGROUND MODE (owner 2026-07-28, the "pointers" case). Two gaps the
# auto-only, black/white-only remover had:
#
#  - AUTO IS A GUESS, and the owner could not overrule it. detect()
#    sniffs the border and picks white/black, or gives up
#    ("skip-ambiguous"). BG_MODE_BLACK/BG_MODE_WHITE let him STATE the
#    background instead, skipping the sniff entirely.
#  - ONLY BLACK AND WHITE existed. The two removals were hard-wired to
#    two scalar keys (max channel / min channel). BG_MODE_COLOR takes
#    ANY target colour plus a per-channel tolerance — the owner's own
#    formulation: "#FF0000 +- X%" spans #EE0000..#FF1111 at X = 6.67 %
#    (17 of 255 per channel), i.e. a CHEBYSHEV box around the target.
#
# The three are ONE mechanism (root Rule #19 — define the rule, never
# enumerate the cases): bg_remove.remove_color_background keys on the
# per-channel distance from a target colour, and black (#000000) and
# white (#FFFFFF) are just two targets. A custom removal at #000000 is
# therefore a fully tunable black removal, which is why the black path
# needs no tolerance knob of its own.
BG_MODE_AUTO = "auto"    # sniff the border: white, black, or give up
BG_MODE_BLACK = "black"  # forced — skip the sniff
BG_MODE_WHITE = "white"  # forced — skip the sniff
BG_MODE_COLOR = "color"  # forced — BG_COLOR target +- BG_COLOR_TOLERANCE_PCT
BG_MODE_DEFAULT = BG_MODE_AUTO
# GUI labels (the BG panel's mode dropdown), keyed by mode. The stored
# settings key is the MODE, never the label, so relabelling the dropdown
# never invalidates a saved settings.json.
BG_MODE_LABEL = {
    BG_MODE_AUTO: "Auto (detect)",
    BG_MODE_BLACK: "Black",
    BG_MODE_WHITE: "White",
    BG_MODE_COLOR: "Custom color",
}

# ═══════════════════════════════ REACH ═════════════════════════════════
# REACH — WHERE a matching pixel counts as background (owner
# 2026-07-28). The removal has always been BORDER-CONNECTED: a pixel
# only counts if it can be walked to from the image frame through other
# matching pixels (a flood fill). That is why pure-#000000 pixels
# ENCLOSED by a letter stroke — the counters of O, A, P in HOPE /
# SALVATION — survive: they are the same colour as the background but
# they are not reachable from the frame.
#
# That is the right default (it protects the black leading between
# stained glass, Aurora's own black hour sector, every dark interior),
# but it is not always what is wanted. BG_REACH_ALL drops the
# connectivity test entirely: EVERY pixel within tolerance goes, wherever
# it sits — the letters become outlines. His call, per run.
BG_REACH_EDGE = "edge"  # border-connected only (flood fill) — default
BG_REACH_ALL = "all"    # every matching pixel, enclosed ones included
BG_REACH_DEFAULT = BG_REACH_EDGE
BG_REACH_LABEL = {
    BG_REACH_EDGE: "Touching the edge",
    BG_REACH_ALL: "Everywhere in the image",
}

# ═══════════════ CUSTOM COLOR + AUTO-DETECTION ══════════════════════════
BG_COLOR_DEFAULT = "#000000"    # custom-colour target, hex
# DEFAULT ONLY — the BG panel's own "+-" field is the fine-tune, and
# 0 is a legal value there (owner 2026-07-28: "MOZE i 0 TOLERANCE AKO
# HOCE tj samo taj HEX" — tolerance 0 keys EXACTLY the typed colour).
BG_COLOR_TOLERANCE_PCT = 6.0    # +- this % of 255 per channel (6 % = +-15)

# AUTO COLOUR DETECTION (owner 2026-07-28). Auto used to give up on
# anything that was not white or black. His rule for finding the
# background colour: look at the FOUR CORNERS, a few pixels deep — if
# they hold the same colour, THAT is the background.
#
# The corners, not the whole border band: a medallion that touches the
# top edge still leaves all four corners clear, so a corner vote is far
# harder to pollute than the border median the white/black sniff uses.
# Disagreeing corners (a gradient, a scene) stay "ambiguous" — the tool
# still never guesses.
AUTO_CORNER_PX = 8         # side of each sampled corner square, px
AUTO_CORNER_AGREE_MAX = 10 # the 4 corner medians agree within this,
#                            per channel (0-255) -> that is the colour
# CUSTOM-COLOUR path guard. Deliberately HIGH, like the white one and
# unlike black's 0.40: black's tight guard is a fence around a GUESS
# (auto keyed a dark subject as background), while a custom colour is
# something the owner TYPED, or one the four corners AGREED on — either
# way the background is known, not inferred from one median, so the
# guard only needs to catch a catastrophic "cleared the whole image".
# The "pointers" plates, whose legitimate background is 42 %, are
# exactly the shape class black's 0.40 bails on.
#
# All three guards are FRACTIONS here because the engine compares them
# against a fraction; the GUI shows and takes them as PERCENT (owner
# 2026-07-28 — "sta znace ti brojevi 0.4, 0.85": a bare 0.40 in a box
# means nothing, 40 % does), converting at the panel edge.
SAFETY_MAX_REMOVE_FRAC_COLOR = 0.85
