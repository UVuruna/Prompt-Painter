#!/usr/bin/env python3
"""Background remover for the medallion / globe asset plates.

Point it at a folder and it makes every image's background transparent,
choosing the method PER FILE automatically:

  * white plate   -> removes the white / off-white border, keeps interior
                     bright detail (edge-connected flood fill + soft edge).
  * globe render  -> clears the BORDER-CONNECTED black void around the
                     subject, keeps dark interior regions ENCLOSED by the
                     subject intact (same edge-connected flood as white,
                     ~1px feather).
  * already transparent, or an ambiguous background (gradient, mid-tone)
                  -> SKIPPED, left untouched. Re-running a folder is safe.

A SAFETY GUARD wraps both removals: if a removal would clear more than
``SAFETY_MAX_REMOVE_FRAC`` of the image (it ate the subject, not just
the background), it is ABORTED and the source is left untouched.

Typical use (the launcher does exactly this):

    python bg_remove.py "greek" --in-place --crop --backup

Auto-detection means you normally pass nothing but the folder name.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

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
        BLACK_VOID_MAX,
        CLEAN_EDGE_ALPHA,
        CROP_INK_ALPHA,
        CROP_MIN_INK_PX,
        SAFETY_MAX_REMOVE_FRAC,
        SAFETY_MAX_REMOVE_FRAC_WHITE,
    )
except ImportError:  # standalone: script's own dir is on sys.path
    from config import (  # type: ignore[no-redef]
        BLACK_VOID_MAX,
        CLEAN_EDGE_ALPHA,
        CROP_INK_ALPHA,
        CROP_MIN_INK_PX,
        SAFETY_MAX_REMOVE_FRAC,
        SAFETY_MAX_REMOVE_FRAC_WHITE,
    )

# --- white mode -------------------------------------------------------------
WHITE_FULL = 250   # whiteness >= this  -> pure background   -> alpha 0
WHITE_EDGE = 200   # whiteness  < this  -> definitely subject -> alpha 255

# --- black mode -------------------------------------------------------------
# BLACK_VOID_MAX (config) is the void brightness ceiling; the removal is
# border-connected, so only the void that TOUCHES the frame is cleared.
FEATHER_SIGMA = 0.8  # Gaussian sigma for the anti-aliased edge (~1px feather)

# --- auto-detection ---------------------------------------------------------
WHITE_BG_MIN = 200   # border median min-channel >= this -> white background
BLACK_BG_MAX = 24    # border median max-channel <= this -> black background
TRANSPARENT_FRAC = 0.02  # already this fraction transparent -> treat as done

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# --------------------------------------------------------------------------- #
# white-background removal
# --------------------------------------------------------------------------- #
def whiteness(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel 'how white' score in 0..255 (high only if every channel high)."""
    return rgb.min(axis=2)


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


def remove_white_border(img: Image.Image,
                        white_full: int = WHITE_FULL,
                        white_edge: int = WHITE_EDGE,
                        ) -> tuple[Image.Image, float]:
    """(RGBA copy, removed_frac) — edge-connected white made transparent.

    ``removed_frac`` is the fraction of the image the removal clears
    (the border-connected white mask); the caller's SAFETY guard aborts
    when it is too high (a white/light subject the flood leaked into)."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    w = whiteness(rgb)
    background = edge_connected_background(w >= white_edge)
    ramp = np.clip((white_full - w) / (white_full - white_edge), 0.0, 1.0)
    alpha = np.where(background, 255.0 * ramp, 255.0)
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA"), float(background.mean())


# --------------------------------------------------------------------------- #
# black-background removal (bright subject on a black void)
# --------------------------------------------------------------------------- #
def brightness(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel brightness (max channel: blue glow / city lights read as high)."""
    return rgb.max(axis=2)


def remove_black_background(img: Image.Image,
                            void_max: int = BLACK_VOID_MAX,
                            sigma: float = FEATHER_SIGMA,
                            ) -> tuple[Image.Image, float]:
    """(RGBA copy, removed_frac) — the BORDER-CONNECTED black void cleared.

    Only near-black pixels (brightness <= ``void_max``) that CONNECT TO
    THE IMAGE BORDER are removed — the corner void. Interior dark
    regions ENCLOSED by the subject (the black leading between glass,
    dark inner areas) are not border-connected and stay OPAQUE. This
    replaces the old "biggest bright blob + fill holes" disc, which
    could not tell a dark subject from a black background and ate dark
    frames (the bible/dark rondels). ``removed_frac`` is the fraction
    the removal clears; the caller's SAFETY guard aborts when the flood
    leaked along a dark ring and over-removed."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    background = edge_connected_background(brightness(rgb) <= void_max)
    keep = (~background).astype(np.float32)
    alpha = np.clip(ndimage.gaussian_filter(keep, sigma), 0.0, 1.0) * 255.0
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA"), float(background.mean())


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
    arr = np.asarray(img.convert("RGBA")).copy()
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


def detect(img: Image.Image):
    """Decide how to treat one image.

    Returns (action, white_full, white_edge). action is one of
    'white', 'black', 'skip-transparent', 'skip-ambiguous'.
    """
    rgba = img.convert("RGBA")
    if (np.asarray(rgba)[:, :, 3] < 250).mean() > TRANSPARENT_FRAC:
        return "skip-transparent", None, None

    rgb = np.asarray(rgba.convert("RGB"))
    border = _border_pixels(rgb)
    if np.median(border.min(axis=1)) >= WHITE_BG_MIN:
        whiteish = border.min(axis=1)
        level = int(np.median(whiteish[whiteish >= WHITE_BG_MIN]))
        white_full = int(np.clip(level - 4, 235, 252))
        white_edge = int(np.clip(white_full - 45, 150, white_full - 10))
        return "white", white_full, white_edge
    if np.median(border.max(axis=1)) <= BLACK_BG_MAX:
        return "black", None, None
    return "skip-ambiguous", None, None


def process_file(src: Path, dst: Path, mode: str, crop: bool,
                 force_full: int | None, force_edge: int | None) -> str:
    """Process one image; returns the action taken (or a 'skip-*' reason).

    'skip-risky' means the SAFETY guard fired: the removal would clear
    more than the path's guard fraction (``SAFETY_MAX_REMOVE_FRAC`` for
    black, ``SAFETY_MAX_REMOVE_FRAC_WHITE`` for white — white legit
    backgrounds run large), i.e. it ate the subject, so the source is
    LEFT UNTOUCHED — nothing is written."""
    with Image.open(src) as im:
        if mode == "auto":
            action, wf, we = detect(im)
        else:
            action, wf, we = mode, WHITE_FULL, WHITE_EDGE
        if force_full is not None:
            wf = force_full
        if force_edge is not None:
            we = force_edge
        if action.startswith("skip"):
            return action
        if action == "white":
            out, removed = remove_white_border(im, wf, we)
            guard = SAFETY_MAX_REMOVE_FRAC_WHITE
        else:
            out, removed = remove_black_background(im)
            guard = SAFETY_MAX_REMOVE_FRAC
    if removed > guard:
        return "skip-risky"  # ate the subject — leave the source untouched
    if crop:
        out = autocrop(out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "PNG", optimize=True)
    return action


def iter_images(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path, help="input image file OR folder")
    ap.add_argument("-o", "--out", type=Path,
                    help="output file/folder (default: '<name>_clean')")
    ap.add_argument("--mode", choices=("auto", "white", "black"), default="auto",
                    help="auto (default) detects white vs black per file")
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
                                  args.white_full, args.white_edge)
            counts[action] = counts.get(action, 0) + 1
            elapsed = time.time() - start
            print(f"[{elapsed:5.1f}s] {i:>4}/{len(files)} | {action:16} | "
                  f"{src.relative_to(args.src)}")
        print(f"\nDone in {time.time() - start:.1f}s:")
        for action, n in sorted(counts.items()):
            print(f"  {action:16} {n}")
        if counts.get("skip-ambiguous"):
            print("  NOTE: 'skip-ambiguous' files had a non-white/non-black "
                  "background and were left untouched — tell me about those.")
        if counts.get("skip-risky"):
            print("  NOTE: 'skip-risky' files would have lost too much to "
                  f"the removal (black > {SAFETY_MAX_REMOVE_FRAC:.0%}, white > "
                  f"{SAFETY_MAX_REMOVE_FRAC_WHITE:.0%} — it ate the subject) "
                  "and were LEFT UNTOUCHED — do those by hand.")
    else:
        if args.in_place:
            dst = args.src
        else:
            dst = args.out or args.src.with_name(args.src.stem + "_clean.png")
        action = process_file(args.src, dst, args.mode, args.crop,
                              args.white_full, args.white_edge)
        print(f"{action} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
