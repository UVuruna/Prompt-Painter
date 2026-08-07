#!/usr/bin/env python3
"""Background remover for the medallion / globe asset plates.

ONE ENGINE, several recipes (root Rule #19 — define the rule, never
enumerate the cases). ``remove_color_background`` clears the BORDER-
CONNECTED region within a per-channel distance of a TARGET COLOUR;
white, black and any custom colour are just three targets:

  * white plate   -> target #FFFFFF, soft two-threshold edge: removes the
                     white / off-white border, keeps interior bright
                     detail.
  * globe render  -> target #000000: clears the black void around the
                     subject, keeps dark interior regions ENCLOSED by the
                     subject intact (never border-connected), ~1px feather.
  * custom colour -> any target the owner types plus a +- tolerance
                     (owner 2026-07-28) — "#FF0000 +- 6.67 %" spans
                     #EE0000..#FF1111, a Chebyshev box around the target.
  * already transparent, or (in auto mode) an ambiguous background
                  -> SKIPPED, left untouched. Re-running a folder is safe.

``plan()`` decides WHICH recipe one image gets: ``BG_MODE_AUTO`` sniffs
the border (white / black / give up), while ``BG_MODE_BLACK``/``_WHITE``/
``_COLOR`` are the owner STATING it and skip the sniff.

A SAFETY GUARD wraps every removal: if it would clear more than the
path's ``SAFETY_GUARD_DEFAULT`` fraction (it ate the subject, not just
the background), it is ABORTED and the source is left untouched.

Typical use (the launcher does exactly this):

    python bg_remove.py "greek" --in-place --crop --backup
    python bg_remove.py "pointers" --in-place --mode color \\
        --color "#000000" --tolerance 6

Auto-detection means you normally pass nothing but the folder name.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image
from scipy import ndimage

# The ink-crop / edge-cleanup thresholds live in config.py (the single
# home for tunables). This module is ALSO runnable as a standalone
# script (`python painter/bg_remove.py ...`), where `painter` is not an
# importable package but config.py sits right beside it — hence the two
# import forms. Both fail loudly if config.py is genuinely missing.
try:
    from painter.config import (
        AUTO_CORNER_AGREE_MAX,
        AUTO_CORNER_PX,
        BG_COLOR_DEFAULT,
        BG_COLOR_TOLERANCE_PCT,
        BG_MODE_AUTO,
        BG_MODE_BLACK,
        BG_MODE_COLOR,
        BG_MODE_WHITE,
        BG_REACH_ALL,
        BG_REACH_DEFAULT,
        BG_REACH_EDGE,
        BLACK_VOID_MAX,
        CLEAN_EDGE_ALPHA,
        CROP_INK_ALPHA,
        CROP_MIN_INK_PX,
        PNG_SAVE_KWARGS,
        SAFETY_MAX_REMOVE_FRAC,
        SAFETY_MAX_REMOVE_FRAC_COLOR,
        SAFETY_MAX_REMOVE_FRAC_WHITE,
    )
except ImportError:  # standalone: script's own dir is on sys.path
    from config import (  # type: ignore[no-redef]
        AUTO_CORNER_AGREE_MAX,
        AUTO_CORNER_PX,
        BG_COLOR_DEFAULT,
        BG_COLOR_TOLERANCE_PCT,
        BG_MODE_AUTO,
        BG_MODE_BLACK,
        BG_MODE_COLOR,
        BG_MODE_WHITE,
        BG_REACH_ALL,
        BG_REACH_DEFAULT,
        BG_REACH_EDGE,
        BLACK_VOID_MAX,
        CLEAN_EDGE_ALPHA,
        CROP_INK_ALPHA,
        CROP_MIN_INK_PX,
        PNG_SAVE_KWARGS,
        SAFETY_MAX_REMOVE_FRAC,
        SAFETY_MAX_REMOVE_FRAC_COLOR,
        SAFETY_MAX_REMOVE_FRAC_WHITE,
    )

# --- white recipe -----------------------------------------------------------
WHITE_RGB = (255, 255, 255)
WHITE_FULL = 250   # whiteness >= this  -> pure background   -> alpha 0
WHITE_EDGE = 200   # whiteness  < this  -> definitely subject -> alpha 255

# --- black recipe -----------------------------------------------------------
# BLACK_VOID_MAX (config) is the void brightness ceiling; the removal is
# border-connected, so only the void that TOUCHES the frame is cleared.
BLACK_RGB = (0, 0, 0)
FEATHER_SIGMA = 0.8  # Gaussian sigma for the anti-aliased edge (~1px feather)

# --- auto-detection ---------------------------------------------------------
WHITE_BG_MIN = 200   # border median min-channel >= this -> white background
BLACK_BG_MAX = 24    # border median max-channel <= this -> black background
TRANSPARENT_FRAC = 0.02  # already this fraction transparent -> treat as done

# Which SAFETY guard fraction each recipe answers to. One mapping, read
# by both callers (this script's process_file and postprocess.remove_
# background) instead of two copies of the same if/else (Rule #5).
SAFETY_GUARD_DEFAULT = {
    BG_MODE_BLACK: SAFETY_MAX_REMOVE_FRAC,
    BG_MODE_WHITE: SAFETY_MAX_REMOVE_FRAC_WHITE,
    BG_MODE_COLOR: SAFETY_MAX_REMOVE_FRAC_COLOR,
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# --------------------------------------------------------------------------- #
# colour parsing (the custom-colour recipe's owner-facing input)
# --------------------------------------------------------------------------- #
def parse_hex_color(text: str) -> tuple[int, int, int]:
    """'#FF0000' / 'ff0000' / '#f00' -> (255, 0, 0).

    Loud ``ValueError`` on anything else — a mistyped background colour
    must never silently fall back to some other colour (Rule #1)."""
    raw = text.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    try:
        if len(raw) != 6:
            raise ValueError
        value = int(raw, 16)
    except ValueError:
        raise ValueError(
            f"background color: {text!r} is not a hex color like #FF0000."
        ) from None
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def format_hex_color(rgb) -> str:
    """(58, 95, 125) -> '#3A5F7D' — how a sniffed border colour is
    reported back to the owner so he can paste it into the custom
    field."""
    r, g, b = (int(round(float(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def tolerance_to_distance(tolerance_pct: float) -> int:
    """The owner's '+- X %' as a per-channel distance in 0..255.

    His own worked example (2026-07-28): '#FF0000 +- X%' spanning
    #EE0000..#FF1111 is +-0x11 = +-17 levels, i.e. X = 6.67 %."""
    if not (0.0 <= tolerance_pct <= 100.0):
        raise ValueError(
            "background tolerance: must be between 0 and 100 %."
        )
    return int(round(tolerance_pct / 100.0 * 255.0))


# --------------------------------------------------------------------------- #
# the ONE removal engine — every recipe is this function's parameters
# --------------------------------------------------------------------------- #
def color_distance(rgb: np.ndarray, target) -> np.ndarray:
    """Per-pixel CHEBYSHEV distance (0..255) from ``target``.

    The LARGEST per-channel difference, so "within distance D" means
    every channel is within +-D — exactly the owner's '#RRGGBB +- X%'
    box. This one key subsumes both historical scalar keys: the
    distance from black is ``max(r, g, b)`` (the old ``brightness``)
    and the distance from white is ``255 - min(r, g, b)`` (255 minus
    the old ``whiteness``), both EXACTLY, so black and white lost no
    tuning when they became targets."""
    return np.abs(rgb - np.asarray(target, dtype=np.float32)).max(axis=2)


def rgba_array(img: Image.Image) -> np.ndarray:
    """The image as ONE ``(H, W, 4)`` uint8 array — THE single decode +
    mode-convert every consumer below shares (owner decree 2026-08-07,
    Priority A).

    One image used to be converted FIVE times per removal: ``plan``
    built an RGBA copy for the alpha check and an RGB copy for the
    border sniff, then ``remove_color_background`` built its own RGB
    copy of the same pixels, and ``clean_edge_halo`` another RGBA one.
    Every convert walks every pixel and allocates a full frame. Now the
    caller builds this once and hands it down; RGB is a free VIEW of it
    (``arr[:, :, :3]``), and the alpha channel is ``arr[:, :, 3]``."""
    return np.asarray(img.convert("RGBA") if img.mode != "RGBA" else img)


def edge_connected_background(candidate: np.ndarray) -> np.ndarray:
    """Boolean mask: candidate pixels that touch, or connect to, the border."""
    labels, n = ndimage.label(candidate)          # 4-connectivity (default)
    if n == 0:
        return np.zeros_like(candidate, dtype=bool)
    border = np.concatenate(
        [labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]
    )
    border_labels = np.unique(border)
    border_labels = border_labels[border_labels != 0]
    return np.isin(labels, border_labels)


def remove_color_background(img: Image.Image,
                            target: tuple[int, int, int],
                            dist_full: int,
                            dist_edge: int,
                            sigma: float = 0.0,
                            reach: str = BG_REACH_DEFAULT,
                            rgba: np.ndarray | None = None,
                            ) -> tuple[Image.Image, float]:
    """(RGBA copy, removed_frac) — the region within ``dist_edge`` of
    ``target`` made transparent. THE engine: white, black and custom
    colour are this function with different arguments.

    ``reach`` decides WHERE a matching pixel counts as background:

    * ``BG_REACH_EDGE`` (default) — only pixels that CONNECT TO THE
      IMAGE BORDER through other matching pixels, i.e. a flood fill
      inward from the frame. A matching region ENCLOSED by the subject
      (the black leading between glass, Aurora's own black hour sector,
      the counters inside the letters of HOPE / SALVATION) is not
      reachable from the frame and stays fully OPAQUE even though it is
      the very same colour. This is what replaced the old "biggest
      bright blob + fill holes" disc, which could not tell a dark
      subject from a black background and ate dark frames (the
      bible/dark rondels).
    * ``BG_REACH_ALL`` (owner 2026-07-28) — no connectivity test at
      all: EVERY pixel within tolerance goes, wherever it sits. The
      enclosed counters become holes and the letters become outlines.

    Two EDGE treatments, chosen by the two distances:

    * ``dist_edge > dist_full`` — a soft two-threshold ramp: alpha 0 at
      or below ``dist_full``, linearly up to 255 at ``dist_edge``. The
      WHITE recipe's own soft edge (its ``white_full``/``white_edge``
      pair read as distances from #FFFFFF).
    * ``dist_edge <= dist_full`` — a HARD cut at ``dist_edge``, which
      ``sigma`` > 0 then feathers into a ~1px anti-aliased edge. The
      BLACK and CUSTOM-COLOUR recipes.

    ``removed_frac`` is the fraction the mask clears; the caller's
    SAFETY guard aborts when it is too high (the flood leaked along a
    dark ring and ate the subject)."""
    # ``rgba``: the caller's already-built array (see rgba_array) —
    # RGB is a view of it, float32 for the distance maths
    source = rgba_array(img) if rgba is None else rgba
    rgb = source[:, :, :3].astype(np.float32)
    dist = color_distance(rgb, target)
    match = dist <= dist_edge
    background = (
        match if reach == BG_REACH_ALL else edge_connected_background(match)
    )
    if dist_edge > dist_full:
        ramp = np.clip(
            (dist - dist_full) / (dist_edge - dist_full), 0.0, 1.0
        )
        alpha = np.where(background, ramp, 1.0).astype(np.float32)
    else:
        alpha = (~background).astype(np.float32)
    if sigma > 0:
        alpha = np.clip(ndimage.gaussian_filter(alpha, sigma), 0.0, 1.0)
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA"), float(background.mean())


def apply_plan(img: Image.Image,
               removal: "RemovalPlan",
               reach: str = BG_REACH_DEFAULT,
               rgba: np.ndarray | None = None,
               ) -> tuple[Image.Image, float]:
    """Run the engine with one ``plan()`` result's parameters.

    ``reach`` is NOT part of the plan: it is orthogonal to WHICH colour
    is the background (every mode, detected or stated, can be run
    either way), so it stays a caller's choice rather than something
    detection decides."""
    return remove_color_background(
        img, removal.target, removal.dist_full, removal.dist_edge,
        removal.sigma, reach, rgba,
    )


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def content_bbox(img: Image.Image,
                 ink_alpha: int = CROP_INK_ALPHA,
                 min_ink_px: int = CROP_MIN_INK_PX,
                 ) -> tuple[int, int, int, int] | None:
    """INK-BASED content bounding box (l, t, r, b) of an RGBA image.

    A row or column counts as content only when it holds at least
    ``min_ink_px`` pixels that are at least ``ink_alpha`` opaque, so a
    sparse faint stray line hugging the border does NOT extend the box
    (the OldAge.png case), while a genuinely wide soft region still
    registers. ``None`` when no row/column qualifies (fully
    transparent, or only faint speckle)."""
    alpha = np.asarray(img)[:, :, 3]
    solid = alpha >= ink_alpha
    cols = np.where(solid.sum(axis=0) >= min_ink_px)[0]
    rows = np.where(solid.sum(axis=1) >= min_ink_px)[0]
    if len(cols) == 0 or len(rows) == 0:
        return None
    return (int(cols.min()), int(rows.min()),
            int(cols.max()) + 1, int(rows.max()) + 1)


def clean_edge_halo(img: Image.Image,
                    edge_alpha: int = CLEAN_EDGE_ALPHA,
                    ) -> tuple[Image.Image, int]:
    """Zero the faint BORDER-CONNECTED halo of an RGBA image.

    Faint pixels (alpha < ``edge_alpha``) that connect to the image
    border — the stray line / halo living in the transparent frame —
    have their alpha set to 0; faint pixels enclosed by the solid
    subject (interior soft edges) are never border-connected and stay
    untouched (this is deliberately NOT a global ``alpha[alpha<K]=0``,
    which would nibble genuine soft edges). Returns the cleaned RGBA
    copy and the count of pixels that actually lost visible alpha."""
    arr = rgba_array(img).copy()
    alpha = arr[:, :, 3]
    halo = edge_connected_background(alpha < edge_alpha)
    cleaned = int(np.count_nonzero(halo & (alpha > 0)))
    arr[:, :, 3] = np.where(halo, 0, alpha)
    return Image.fromarray(arr, mode="RGBA"), cleaned


def autocrop(img: Image.Image,
             ink_alpha: int = CROP_INK_ALPHA,
             min_ink_px: int = CROP_MIN_INK_PX) -> Image.Image:
    """Crop to the ink-based content box (see ``content_bbox``)."""
    box = content_bbox(img, ink_alpha, min_ink_px)
    if box is None:
        return img
    return img.crop(box)


def _border_pixels(rgb: np.ndarray) -> np.ndarray:
    """Flat list of the outer-frame pixels (used to sniff the background)."""
    h, w = rgb.shape[:2]
    band = max(8, int(min(h, w) * 0.01))
    parts = [rgb[:band], rgb[-band:], rgb[:, :band], rgb[:, -band:]]
    return np.concatenate([p.reshape(-1, 3) for p in parts])


class RemovalPlan(NamedTuple):
    """How ONE image is to be treated — ``plan()``'s answer.

    ``action`` is 'white' / 'black' / 'color' (run the engine with the
    fields below) or 'skip-transparent' / 'skip-ambiguous' (do nothing;
    the colour fields are then placeholders). ``border_hex`` is ALWAYS
    the sniffed border colour, so an ambiguous skip can tell the owner
    WHICH colour to type into the custom-colour field instead of just
    giving up (Rule #1 — a report he can act on)."""

    action: str
    target: tuple[int, int, int]
    dist_full: int
    dist_edge: int
    sigma: float
    border_hex: str


SKIP_PLAN_COLOR = (BLACK_RGB, 0, 0, 0.0)  # placeholders for a skip plan


def _white_plan(border: np.ndarray, border_hex: str) -> RemovalPlan:
    """The white recipe, its thresholds ADAPTED to this plate's own
    white level (an off-white plate keys at its own value, not at a
    fixed 250), falling back to the module defaults when the border
    holds no whiteish pixels at all — only reachable in FORCED white
    mode, since auto only gets here past a whiteish border median."""
    whiteish = border.min(axis=1)
    bright = whiteish[whiteish >= WHITE_BG_MIN]
    if bright.size:
        level = int(np.median(bright))
        white_full = int(np.clip(level - 4, 235, 252))
        white_edge = int(np.clip(white_full - 45, 150, white_full - 10))
    else:
        white_full, white_edge = WHITE_FULL, WHITE_EDGE
    # as DISTANCES from #FFFFFF: whiteness w maps to distance 255 - w,
    # so the pair keeps its exact historical meaning and ramp
    return RemovalPlan(
        BG_MODE_WHITE, WHITE_RGB, 255 - white_full, 255 - white_edge,
        0.0, border_hex,
    )


def _black_plan(border_hex: str) -> RemovalPlan:
    return RemovalPlan(
        BG_MODE_BLACK, BLACK_RGB, BLACK_VOID_MAX, BLACK_VOID_MAX,
        FEATHER_SIGMA, border_hex,
    )


def corner_background_color(rgb: np.ndarray,
                            corner_px: int = AUTO_CORNER_PX,
                            agree_max: int = AUTO_CORNER_AGREE_MAX,
                            ) -> tuple[int, int, int] | None:
    """The background colour the FOUR CORNERS agree on, else ``None``.

    The owner's own rule for auto-detecting a colour (2026-07-28):
    sample each corner a few pixels deep, and if they all hold the same
    colour, that IS the background. Each corner contributes its own
    median; they AGREE when the spread across the four is within
    ``agree_max`` on every channel.

    The corners rather than the whole border band, because they are the
    part of the frame least likely to hold the subject — a medallion
    touching the top edge still leaves all four clear, while it would
    drag the border median. Disagreeing corners (a gradient, a scene)
    return ``None`` and the image stays 'ambiguous': the tool reports
    rather than guesses."""
    height, width = rgb.shape[:2]
    side = max(1, min(corner_px, height, width))
    corners = (rgb[:side, :side], rgb[:side, -side:],
               rgb[-side:, :side], rgb[-side:, -side:])
    medians = np.array(
        [np.median(c.reshape(-1, 3), axis=0) for c in corners]
    )
    if (medians.max(axis=0) - medians.min(axis=0)).max() > agree_max:
        return None
    return tuple(int(round(v)) for v in np.median(medians, axis=0))


def plan(img: Image.Image,
         mode: str = BG_MODE_AUTO,
         *,
         color: str = BG_COLOR_DEFAULT,
         tolerance_pct: float = BG_COLOR_TOLERANCE_PCT,
         rgba: np.ndarray | None = None,
         ) -> RemovalPlan:
    """Decide how to treat one image (see ``RemovalPlan``).

    ``BG_MODE_AUTO`` sniffs the border for white or black, then falls
    back to the FOUR-CORNER colour vote (``corner_background_color``)
    for any other uniform background, and only gives up
    ('skip-ambiguous') when even the corners disagree.
    ``BG_MODE_BLACK``/``BG_MODE_WHITE``/``BG_MODE_COLOR`` are the owner
    STATING the background and skip the sniff entirely (owner
    2026-07-28).

    An ALREADY-TRANSPARENT image is skipped in EVERY mode, forced ones
    included: it has a real alpha channel that a colour key knows
    nothing about and would overwrite, and this is what makes re-running
    a folder safe."""
    source = rgba_array(img) if rgba is None else rgba
    if (source[:, :, 3] < 250).mean() > TRANSPARENT_FRAC:
        return RemovalPlan("skip-transparent", *SKIP_PLAN_COLOR, "")

    rgb = source[:, :, :3]  # a VIEW, not a third copy of the pixels
    border = _border_pixels(rgb)
    border_hex = format_hex_color(np.median(border, axis=0))

    if mode == BG_MODE_COLOR:
        distance = tolerance_to_distance(tolerance_pct)
        return RemovalPlan(
            BG_MODE_COLOR, parse_hex_color(color), distance, distance,
            FEATHER_SIGMA, border_hex,
        )
    if mode == BG_MODE_BLACK:
        return _black_plan(border_hex)
    if mode == BG_MODE_WHITE:
        return _white_plan(border, border_hex)

    if np.median(border.min(axis=1)) >= WHITE_BG_MIN:
        return _white_plan(border, border_hex)
    if np.median(border.max(axis=1)) <= BLACK_BG_MAX:
        return _black_plan(border_hex)
    # neither white nor black — ask the FOUR CORNERS what colour the
    # background is (owner 2026-07-28). Strictly a fallback: everything
    # the white/black sniff already recognises is untouched by this.
    agreed = corner_background_color(rgb)
    if agreed is not None:
        distance = tolerance_to_distance(tolerance_pct)
        return RemovalPlan(
            BG_MODE_COLOR, agreed, distance, distance, FEATHER_SIGMA,
            format_hex_color(agreed),
        )
    return RemovalPlan("skip-ambiguous", *SKIP_PLAN_COLOR, border_hex)


def process_file(src: Path, dst: Path, mode: str, crop: bool,
                 force_full: int | None, force_edge: int | None,
                 color: str = BG_COLOR_DEFAULT,
                 tolerance_pct: float = BG_COLOR_TOLERANCE_PCT,
                 reach: str = BG_REACH_DEFAULT) -> str:
    """Process one image; returns the action taken (or a 'skip-*' reason).

    'skip-risky' means the SAFETY guard fired: the removal would clear
    more than the path's ``SAFETY_GUARD_DEFAULT`` fraction (black is
    tight at 0.40, white and custom colour run high because their legit
    backgrounds are large), i.e. it ate the subject, so the source is
    LEFT UNTOUCHED — nothing is written.

    ``force_full``/``force_edge`` are the CLI's white-threshold
    overrides, still expressed as WHITENESS levels (--white-full /
    --white-edge) and converted to distances from #FFFFFF here."""
    with Image.open(src) as im:
        pixels = rgba_array(im)  # ONE convert for plan + engine both
        removal = plan(
            im, mode, color=color, tolerance_pct=tolerance_pct,
            rgba=pixels,
        )
        if removal.action.startswith("skip"):
            return removal.action
        if force_full is not None:
            removal = removal._replace(dist_full=255 - force_full)
        if force_edge is not None:
            removal = removal._replace(dist_edge=255 - force_edge)
        out, removed = apply_plan(im, removal, reach, rgba=pixels)
    if removed > SAFETY_GUARD_DEFAULT[removal.action]:
        return "skip-risky"  # ate the subject — leave the source untouched
    if crop:
        out = autocrop(out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "PNG", **PNG_SAVE_KWARGS)
    return removal.action


def iter_images(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path, help="input image file OR folder")
    ap.add_argument("-o", "--out", type=Path,
                    help="output file/folder (default: '<name>_clean')")
    ap.add_argument("--mode",
                    choices=(BG_MODE_AUTO, BG_MODE_WHITE, BG_MODE_BLACK,
                             BG_MODE_COLOR),
                    default=BG_MODE_AUTO,
                    help="auto (default) detects white vs black per file;"
                         " white/black force one; color keys on --color")
    ap.add_argument("--color", default=BG_COLOR_DEFAULT,
                    help="--mode color target, hex (default %(default)s)")
    ap.add_argument("--tolerance", type=float,
                    default=BG_COLOR_TOLERANCE_PCT,
                    help="--mode color +- tolerance, %% of 255 per channel"
                         " (default %(default)s)")
    ap.add_argument("--reach", choices=(BG_REACH_EDGE, BG_REACH_ALL),
                    default=BG_REACH_DEFAULT,
                    help="edge (default) clears only what connects to the"
                         " frame, keeping enclosed same-coloured regions"
                         " (letter counters); all clears every matching"
                         " pixel wherever it sits")
    ap.add_argument("--white-full", type=int, help="override white threshold")
    ap.add_argument("--white-edge", type=int, help="override white edge")
    ap.add_argument("--crop", action="store_true", help="autocrop to the subject")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite each source file instead of writing a copy")
    ap.add_argument("--backup", action="store_true",
                    help="copy the folder to '<name>__backup' once before writing")
    args = ap.parse_args(argv)

    if (args.white_full is not None and args.white_edge is not None
            and args.white_edge >= args.white_full):
        ap.error("--white-edge must be < --white-full")
    if args.in_place and args.out:
        ap.error("--in-place cannot be combined with --out")

    if args.src.is_dir():
        if args.backup:
            bkp = args.src.with_name(args.src.name + "__backup")
            if bkp.exists():
                print(f"Backup already exists, keeping it -> {bkp}")
            else:
                shutil.copytree(args.src, bkp)
                print(f"Backup -> {bkp}")
        out_root = args.out or args.src.with_name(args.src.name + "_clean")
        files = list(iter_images(args.src))
        if not files:
            print(f"No images found under {args.src}")
            return 1
        dest = "in-place" if args.in_place else out_root
        print(f"Processing {len(files)} image(s) from {args.src} -> {dest}")
        counts: dict[str, int] = {}
        start = time.time()
        for i, src in enumerate(files, 1):
            dst = src if args.in_place else out_root / src.relative_to(args.src).with_suffix(".png")
            action = process_file(src, dst, args.mode, args.crop,
                                  args.white_full, args.white_edge,
                                  args.color, args.tolerance, args.reach)
            counts[action] = counts.get(action, 0) + 1
            elapsed = time.time() - start
            print(f"[{elapsed:5.1f}s] {i:>4}/{len(files)} | {action:16} | "
                  f"{src.relative_to(args.src)}")
        print(f"\nDone in {time.time() - start:.1f}s:")
        for action, n in sorted(counts.items()):
            print(f"  {action:16} {n}")
        if counts.get("skip-ambiguous"):
            print("  NOTE: 'skip-ambiguous' files had a non-white/non-black "
                  "background and were left untouched — re-run them with "
                  "--mode color --color '#RRGGBB' to clear that colour.")
        if counts.get("skip-risky"):
            guards = ", ".join(
                f"{name} > {frac:.0%}"
                for name, frac in SAFETY_GUARD_DEFAULT.items()
            )
            print("  NOTE: 'skip-risky' files would have lost too much to "
                  f"the removal ({guards} — it ate the subject) and were "
                  "LEFT UNTOUCHED — raise the guard, or do those by hand.")
    else:
        if args.in_place:
            dst = args.src
        else:
            dst = args.out or args.src.with_name(args.src.stem + "_clean.png")
        action = process_file(args.src, dst, args.mode, args.crop,
                              args.white_full, args.white_edge,
                              args.color, args.tolerance, args.reach)
        print(f"{action} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
