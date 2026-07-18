#!/usr/bin/env python3
"""Background remover for the medallion / globe asset plates.

Point it at a folder and it makes every image's background transparent,
choosing the method PER FILE automatically:

  * white plate   -> removes the white / off-white border, keeps interior
                     bright detail (edge-connected flood fill + soft edge).
  * globe render  -> clears the black void around a bright subject, keeps the
                     dark night side intact (largest bright blob, ~1px feather).
  * already transparent, or an ambiguous background (gradient, mid-tone)
                  -> SKIPPED, left untouched. Re-running a folder is safe.

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

# --- white mode -------------------------------------------------------------
WHITE_FULL = 250   # whiteness >= this  -> pure background   -> alpha 0
WHITE_EDGE = 200   # whiteness  < this  -> definitely subject -> alpha 255

# --- black mode -------------------------------------------------------------
BLACK_SOLID = 6      # brightness >= this -> part of the subject body
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
                        white_edge: int = WHITE_EDGE) -> Image.Image:
    """RGBA copy with the edge-connected white background made transparent."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    w = whiteness(rgb)
    background = edge_connected_background(w >= white_edge)
    ramp = np.clip((white_full - w) / (white_full - white_edge), 0.0, 1.0)
    alpha = np.where(background, 255.0 * ramp, 255.0)
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


# --------------------------------------------------------------------------- #
# black-background removal (bright subject on a black void)
# --------------------------------------------------------------------------- #
def brightness(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel brightness (max channel: blue glow / city lights read as high)."""
    return rgb.max(axis=2)


def subject_disc(b: np.ndarray, solid: int) -> np.ndarray:
    """Solid mask of the subject body: largest bright blob, holes filled."""
    labels, n = ndimage.label(b >= solid)
    if n == 0:
        return np.zeros_like(b, dtype=bool)
    sizes = ndimage.sum(np.ones_like(labels), labels, index=range(1, n + 1))
    biggest = int(np.argmax(sizes)) + 1
    return ndimage.binary_fill_holes(labels == biggest)


def remove_black_background(img: Image.Image,
                            solid: int = BLACK_SOLID,
                            sigma: float = FEATHER_SIGMA) -> Image.Image:
    """RGBA copy with the black void around a bright subject cleared."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    disc = subject_disc(brightness(rgb), solid)
    alpha = np.clip(ndimage.gaussian_filter(disc.astype(np.float32), sigma),
                    0.0, 1.0) * 255.0
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def content_bbox(img: Image.Image,
                 alpha_thresh: int = 8) -> tuple[int, int, int, int] | None:
    """Bounding box (l, t, r, b) of visible pixels of an RGBA image,
    ignoring the feather ring; None when fully transparent."""
    alpha = np.asarray(img)[:, :, 3]
    ys, xs = np.where(alpha >= alpha_thresh)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def autocrop(img: Image.Image, alpha_thresh: int = 8) -> Image.Image:
    """Crop to the bounding box of visible pixels (ignoring the feather ring)."""
    box = content_bbox(img, alpha_thresh)
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
    """Process one image; returns the action taken (or a 'skip-*' reason)."""
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
            out = remove_white_border(im, wf, we)
        else:
            out = remove_black_background(im)
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
