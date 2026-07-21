"""Postprocess — background removal and transparent-crop, composable.

Owner workflow step 6, split in two (owner's #7): the pipeline
callers (main.py's post_save, the GUI's own) compose the steps by
flags instead of one fused fix:

* ``remove_background`` — the in-house remover, auto-detected per
  file: already-transparent images are untouched ("nothing"), white
  (Gemini) and black backgrounds are cleared ("done"), ambiguous
  ones are reported and left alone ("unclear").
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
    CLEAN_EDGE_ALPHA,
    CLEAN_EDGE_ENABLE,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    CROP_MIN_INK_PX,
    SAFETY_MAX_REMOVE_FRAC,
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
    safety_max_remove_frac: float = SAFETY_MAX_REMOVE_FRAC,
    safety_max_remove_frac_white: float = SAFETY_MAX_REMOVE_FRAC_WHITE,
) -> str:
    """Clear one saved image's background in place.

    Returns "done" (white/black background cleared), "nothing"
    (already transparent — no-op) or "unclear" (ambiguous background,
    OR the SAFETY guard fired: the removal would clear more than the
    path's guard fraction — it ate the subject — so the ORIGINAL is
    left untouched and reported for manual handling). Raises
    ``PostprocessError`` on a real failure.

    ``safety_max_remove_frac``/``safety_max_remove_frac_white``
    (GUI rework Phase 13) are OPTIONAL per-call overrides of the two
    SAFETY GUARD fractions below, defaulting to the config constants —
    every existing caller that passes neither keeps today's exact
    behaviour; ``BgSettingsPanel``'s Advanced collapsible is the one
    caller that overrides them, per run.
    """
    from PIL import Image

    from painter.bg_remove import (
        detect,
        remove_black_background,
        remove_white_border,
    )

    try:
        with Image.open(path) as im:
            action, white_full, white_edge = detect(im)
            if action == "skip-transparent":
                return "nothing"
            if action == "skip-ambiguous":
                log(
                    f"    background UNCLEAR (not white/black) — left"
                    f" untouched: {path.name}"
                )
                return "unclear"
            if action == "white":
                out, removed = remove_white_border(im, white_full, white_edge)
                guard = safety_max_remove_frac_white
            else:
                out, removed = remove_black_background(im)
                guard = safety_max_remove_frac
        # SAFETY GUARD: never destroy an image. A removal that clears
        # more than the path's guard fraction ate the subject (a dark
        # subject keyed as black background, or a flood that leaked
        # along a dark ring) — abort, leave the ORIGINAL untouched,
        # report loudly. The white guard runs high because legit white
        # backgrounds are large; the black guard is tight (see config).
        if removed > guard:
            log(
                f"    background removal would clear {removed:.0%} —"
                f" too risky, left untouched (do it manually): {path.name}"
            )
            return "unclear"
        out.save(path, "PNG", optimize=True)
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
        rgba.crop((left, top, right, bottom)).save(path, "PNG", optimize=True)
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"crop failed on {path.name}: {exc}"
        ) from exc
