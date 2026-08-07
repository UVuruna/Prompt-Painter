"""Postprocess — background removal and transparent-crop, composable.

Owner workflow step 6, split in two (owner's #7): the pipeline
callers (main.py's post_save, the GUI's own) compose the steps by
flags instead of one fused fix:

* ``remove_background`` — the in-house remover. Its ``mode`` (owner
  2026-07-28) is auto-detect (white/black, ambiguous ones reported
  and left alone — "unclear"), a FORCED white/black, or a CUSTOM
  COLOUR plus tolerance that clears any background colour at all.
  Already-transparent images are untouched ("nothing") in every mode.
* ``crop_transparent`` — autocrop a transparent image to its content
  bounding box plus a small config safety margin ("done"), or leave
  it be when there is no transparency to crop against or it is
  already tight ("nothing").

Both work IN PLACE, only ever on the file they are given (inside
the output folder), loud (``PostprocessError``) on real errors and
silent on no-ops. Heavy imports (numpy/scipy/Pillow) load lazily so
dry runs and sheet checks stay stdlib-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from painter.config import (
    BG_COLOR_DEFAULT,
    BG_COLOR_TOLERANCE_PCT,
    BG_MODE_AUTO,
    BG_MODE_BLACK,
    BG_MODE_COLOR,
    BG_MODE_DEFAULT,
    BG_MODE_WHITE,
    BG_REACH_DEFAULT,
    CLEAN_EDGE_ALPHA,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    PNG_SAVE_KWARGS,
    SAFETY_MAX_REMOVE_FRAC,
    SAFETY_MAX_REMOVE_FRAC_COLOR,
    SAFETY_MAX_REMOVE_FRAC_WHITE,
)

Log = Callable[[str], None]


class PostprocessError(RuntimeError):
    """A postprocess step failed on one image (loud, not masked)."""


def deps_error() -> str | None:
    """None when the postprocess steps can run; else the reason not."""
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as exc:
        return (
            f"postprocess needs numpy, scipy and Pillow ({exc}) —"
            " pip install -r requirements.txt, or disable the"
            " background fix and crop"
        )
    return None


def remove_background(
    path: Path,
    log: Log,
    *,
    mode: str = BG_MODE_DEFAULT,
    color: str = BG_COLOR_DEFAULT,
    tolerance_pct: float = BG_COLOR_TOLERANCE_PCT,
    reach: str = BG_REACH_DEFAULT,
    safety_max_remove_frac: float = SAFETY_MAX_REMOVE_FRAC,
    safety_max_remove_frac_white: float = SAFETY_MAX_REMOVE_FRAC_WHITE,
    safety_max_remove_frac_color: float = SAFETY_MAX_REMOVE_FRAC_COLOR,
) -> str:
    """Clear one saved image's background in place.

    Returns "done" (the background was cleared), "nothing" (already
    transparent — no-op) or "unclear" (an ambiguous background in auto
    mode, OR the SAFETY guard fired: the removal would clear more than
    the path's guard fraction — it ate the subject — so the ORIGINAL is
    left untouched and reported for manual handling). Raises
    ``PostprocessError`` on a real failure.

    ``mode`` (owner 2026-07-28) picks WHICH background is cleared:
    ``BG_MODE_AUTO`` sniffs the border for white or black and then asks
    the FOUR CORNERS for any other uniform colour (only disagreeing
    corners give "unclear"), ``BG_MODE_BLACK``/``BG_MODE_WHITE`` force
    one and skip the sniff, and ``BG_MODE_COLOR`` clears ANY ``color``
    (hex) within ``tolerance_pct`` % of 255 per channel — 0 % keys the
    typed colour EXACTLY. The colour is parsed ONCE, before the image is
    opened, so a mistyped hex is reported as the configuration error it
    is rather than as a per-image failure.

    ``reach`` (owner 2026-07-28) decides WHERE a matching pixel counts:
    ``BG_REACH_EDGE`` clears only what connects to the frame, so an
    enclosed same-coloured region (the counters inside letters) stays;
    ``BG_REACH_ALL`` clears every matching pixel wherever it sits.

    The three ``safety_max_remove_frac*`` arguments (GUI rework Phase
    13; the colour one 2026-07-28) are OPTIONAL per-call overrides of
    the SAFETY GUARD fractions, defaulting to the config constants —
    every caller that passes none keeps today's exact behaviour;
    ``BgSettingsPanel`` is the one caller that overrides them, per run.
    """
    from PIL import Image

    from painter.bg_remove import apply_plan, parse_hex_color, plan

    if mode == BG_MODE_COLOR:
        parse_hex_color(color)  # loud NOW, not once per image
    guards = {
        BG_MODE_BLACK: safety_max_remove_frac,
        BG_MODE_WHITE: safety_max_remove_frac_white,
        BG_MODE_COLOR: safety_max_remove_frac_color,
    }

    try:
        with Image.open(path) as im:
            removal = plan(
                im, mode, color=color, tolerance_pct=tolerance_pct
            )
            if removal.action == "skip-transparent":
                return "nothing"
            if removal.action == "skip-ambiguous":
                # name the sniffed border colour: the owner can paste it
                # straight into the BG panel's custom-colour field
                # instead of being told only that we gave up (Rule #1)
                log(
                    f"    background UNCLEAR (not white/black, and the"
                    f" four corners disagree; border ≈"
                    f" {removal.border_hex}) — left untouched:"
                    f" {path.name}; set BG mode to Custom color to"
                    f" clear it"
                )
                return "unclear"
            if mode == BG_MODE_AUTO and removal.action == BG_MODE_COLOR:
                # an AUTO-DETECTED colour is a decision the owner did not
                # make — say which colour was cleared, never silently
                log(
                    f"    background color auto-detected from the four"
                    f" corners: {removal.border_hex} ({path.name})"
                )
            out, removed = apply_plan(im, removal, reach)
        # SAFETY GUARD: never destroy an image. A removal that clears
        # more than the path's guard fraction ate the subject (a dark
        # subject keyed as black background, or a flood that leaked
        # along a dark ring) — abort, leave the ORIGINAL untouched,
        # report loudly. The white and custom-colour guards run high
        # because their legit backgrounds are large; the black guard is
        # tight (see config), which is why the message NAMES the guard
        # that fired and where to raise it: a legitimate 42%-background
        # plate bailing on black's 0.40 is the owner's "pointers" case,
        # and the old message told him nothing he could act on.
        guard = guards[removal.action]
        if removed > guard:
            log(
                f"    background removal would clear {removed:.0%} of"
                f" {path.name} — over the {removal.action} safety guard"
                f" ({guard:.0%}), left untouched; raise it in BG"
                f" removal → Advanced, or do it manually"
            )
            return "unclear"
        out.save(path, "PNG", **PNG_SAVE_KWARGS)
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"background removal failed on {path.name}: {exc}"
        ) from exc


def crop_transparent(
    path: Path,
    log: Log,
    *,
    clean_edge_enable: bool = CLEAN_EDGE_ENABLE,
    clean_edge_alpha: int = CLEAN_EDGE_ALPHA,
    crop_margin_px: int = CROP_MARGIN_PX,
    crop_ink_alpha: int = CROP_INK_ALPHA,
    crop_min_ink_px: int = CROP_MIN_INK_PX,
) -> str:
    """Clean the faint border halo, then autocrop, in place.

    The halo cleanup (``clean_edge_halo`` when ``clean_edge_enable``)
    only serves to ENABLE a tighter crop: faint pixels connected to the
    image border — the stray line / halo hugging the frame — are zeroed
    so they no longer drag the content box out to the edge. The image is
    then cropped to its INK-BASED content box (a row/col needs
    ``crop_min_ink_px`` pixels at alpha >= ``crop_ink_alpha``, so a
    sparse faint line no longer defeats the crop) plus the
    ``crop_margin_px`` safety margin.

    The rule is strictly DIMENSIONAL (owner 2026-07-19): "done" only when
    the cropped output resolution is SMALLER than the input on some side
    (>= 1px) — that alone saves the file (cleaned + cropped). A box +
    margin that lands on the FULL frame is a 0px change and is SKIPPED —
    "nothing", the file left BYTE-UNCHANGED, even when the halo cleanup
    zeroed pixels (that cleanup is then discarded, never written; there
    is no such thing as a halo-only "done"). Raises ``PostprocessError``
    on a real failure.

    Every keyword above (GUI rework Phase 13) is an OPTIONAL per-call
    override of the matching config constant, so an omitted argument
    reproduces today's exact byte-for-byte behaviour; ``CropSettingsPanel``'s
    Advanced collapsible is the one caller that overrides them, per run.
    """
    from PIL import Image

    from painter.bg_remove import clean_edge_halo, content_bbox

    try:
        with Image.open(path) as im:
            rgba = im.convert("RGBA")

        if clean_edge_enable:
            rgba, _ = clean_edge_halo(rgba, clean_edge_alpha)

        box = content_bbox(rgba, crop_ink_alpha, crop_min_ink_px)
        if box is None:
            # no solid content to crop to (fully transparent / faint
            # speckle only) -> no crop possible -> 0px change -> SKIPPED
            return "nothing"

        width, height = rgba.size
        left = max(0, box[0] - crop_margin_px)
        top = max(0, box[1] - crop_margin_px)
        right = min(width, box[2] + crop_margin_px)
        bottom = min(height, box[3] + crop_margin_px)
        # CHANGED vs SKIPPED by EXACT resolution (owner 2026-07-19): the
        # crop counts ONLY when the output size differs from the input on
        # SOME side (>= 1px). A box + margin that lands on the full frame
        # (0px change) is no crop — SKIPPED — regardless of any halo
        # cleanup, which is discarded rather than saved.
        if (right - left) == width and (bottom - top) == height:
            return "nothing"  # output resolution == input -> no crop
        rgba.crop((left, top, right, bottom)).save(
            path, "PNG", **PNG_SAVE_KWARGS
        )
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"crop failed on {path.name}: {exc}"
        ) from exc
