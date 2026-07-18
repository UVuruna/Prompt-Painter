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


def remove_background(path: Path, log: Log) -> str:
    """Clear one saved image's background in place.

    Returns "done" (white/black background cleared), "nothing"
    (already transparent — no-op) or "unclear" (ambiguous background,
    OR the SAFETY guard fired: the removal would clear more than the
    path's guard fraction — it ate the subject — so the ORIGINAL is
    left untouched and reported for manual handling). Raises
    ``PostprocessError`` on a real failure.
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
                guard = SAFETY_MAX_REMOVE_FRAC_WHITE
            else:
                out, removed = remove_black_background(im)
                guard = SAFETY_MAX_REMOVE_FRAC
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


def crop_transparent(path: Path, log: Log) -> str:
    """Clean the faint border halo, then autocrop, in place.

    Two composable steps on the one image (both from
    [Background Remover]): (1) when ``CLEAN_EDGE_ENABLE``, faint
    pixels connected to the image border — the stray line / halo
    hugging the frame — are zeroed (``clean_edge_halo``); (2) the
    image is cropped to its INK-BASED content box (a row/col needs
    ``CROP_MIN_INK_PX`` pixels at alpha >= ``CROP_INK_ALPHA``, so a
    sparse faint line no longer defeats the crop) plus the
    ``CROP_MARGIN_PX`` safety margin.

    Returns "done" when it changed anything (halo cleaned OR box
    trimmed) or "nothing" — no transparency to crop against (fully
    opaque, so the box IS the image), fully transparent, or already
    tight AND nothing to clean. Raises ``PostprocessError`` on a real
    failure.
    """
    from PIL import Image

    from painter.bg_remove import clean_edge_halo, content_bbox

    try:
        with Image.open(path) as im:
            rgba = im.convert("RGBA")

        cleaned = 0
        if CLEAN_EDGE_ENABLE:
            rgba, cleaned = clean_edge_halo(rgba, CLEAN_EDGE_ALPHA)

        box = content_bbox(rgba, CROP_INK_ALPHA, CROP_MIN_INK_PX)
        if box is None:
            # no solid content to crop to (fully transparent / faint
            # speckle only); a halo cleanup may still have changed it
            if cleaned:
                rgba.save(path, "PNG", optimize=True)
                return "done"
            return "nothing"

        width, height = rgba.size
        left = max(0, box[0] - CROP_MARGIN_PX)
        top = max(0, box[1] - CROP_MARGIN_PX)
        right = min(width, box[2] + CROP_MARGIN_PX)
        bottom = min(height, box[3] + CROP_MARGIN_PX)
        trimmed = (left, top, right, bottom) != (0, 0, width, height)

        if not trimmed and not cleaned:
            return "nothing"  # opaque or already tight, nothing to clean
        result = rgba.crop((left, top, right, bottom)) if trimmed else rgba
        result.save(path, "PNG", optimize=True)
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"crop failed on {path.name}: {exc}"
        ) from exc
