"""Postprocess: background removal + crop (owner workflow step 6).

painter/postprocess.py runs over every saved image; the two steps
are COMPOSABLE (owner's #7): remove_background auto-detects per
file (already-transparent -> nothing, white/black cleared,
ambiguous -> unclear, left untouched); crop_transparent autocrops
a transparent image to its content bounding box.
"""

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
