"""Job temp / before-after / restore — the four in-place tools' safety net.

Owner 2026-07-19: BG removal, Crop, Upscale and Aspect ratio all
overwrite files IN PLACE. Before each op the ORIGINAL is copied into a
per-job temp subdir so the dashboard can (1) show a BEFORE/AFTER viewer
and (2) RESTORE one image or the whole job. The image-generation jobs
make NEW files and never need this.

``JobTemp`` owns one job slot's backups; ``clear_all`` wipes the whole
temp root (app-exit cleanup + a startup orphan sweep). ``measure``
computes the per-tool before→after number the panel shows (% removed /
reduction / increase / deformation) from the temp backup vs the in-place
result — so the engine functions stay unchanged and every metric is
derived OUTSIDE them.

Only the stdlib (shutil / pathlib) loads at import; PIL and numpy load
lazily inside ``measure`` so dry runs and sheet checks stay
stdlib-only.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from painter.config import (
    JOB_METRIC,
    JOBTEMP_DIRNAME,
    JOBTEMP_REMOVED_ALPHA,
    PROJECT_ROOT,
)

# the one temp root; every job slot gets a subdir under it
TEMP_ROOT = PROJECT_ROOT / JOBTEMP_DIRNAME


class JobTemp:
    """One tool job's backup store: back up an ORIGINAL before its
    in-place op, then restore one file or all of them on demand.

    The slot's subdir is FRESH on construction (any stale content from a
    previous run of the same slot is wiped) so a reused panel never
    restores from a foreign job.
    """

    def __init__(self, slot: str, folder: Path):
        self.slot = slot
        self.folder = Path(folder)
        self.root = TEMP_ROOT / slot
        # a reused slot must not inherit an old job's backups
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def backup(self, src: Path, rel: str) -> Path:
        """Copy the ORIGINAL of ``folder/rel`` into the temp store
        BEFORE the tool touches it; returns the backup path."""
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def drop(self, rel: str) -> None:
        """Delete a backup — for a no-op (the file was left unchanged),
        so an unchanged file holds no restore point."""
        bak = self.root / rel
        if bak.exists():
            bak.unlink()

    def before_path(self, rel: str) -> Path | None:
        """The backup (BEFORE) path for ``rel``, or None if there is
        none (a no-op / never-backed-up file)."""
        bak = self.root / rel
        return bak if bak.exists() else None

    def has_backup(self, rel: str) -> bool:
        return (self.root / rel).exists()

    def restore_one(self, rel: str) -> bool:
        """Copy the backup back over ``folder/rel``. Returns False when
        there is no backup (nothing to restore)."""
        bak = self.root / rel
        if not bak.exists():
            return False
        dest = self.folder / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bak, dest)
        return True

    def restore_all(self) -> int:
        """Restore every backed-up file; returns the count restored."""
        count = 0
        for bak in self.root.rglob("*"):
            if bak.is_file():
                rel = bak.relative_to(self.root).as_posix()
                if self.restore_one(rel):
                    count += 1
        return count

    def clear(self) -> None:
        """Wipe this job's whole temp subdir (on panel CLOSE)."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)


def clear_all() -> None:
    """Wipe the WHOLE temp root — app-exit cleanup and a startup sweep
    of any crash-orphaned backups."""
    if TEMP_ROOT.exists():
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)


def _alpha_of(img) -> "object":
    """The alpha channel of one PIL image as a numpy array (255 where a
    mode has no alpha)."""
    import numpy as np

    return np.asarray(img.convert("RGBA"))[:, :, 3].copy()


def measure(kind: str, before: Path, after: Path) -> dict:
    """The before→after number one tool panel shows for one image.

    Returns ``{'before': 'WxH', 'after': 'WxH', 'pct': float,
    'label': str}``:

    * ``bg``     — % of pixels whose alpha fell below
      ``JOBTEMP_REMOVED_ALPHA`` (removal never resizes, so before/after
      share WxH).
    * ``crop``   — % area REDUCTION (the result is smaller).
    * ``upscale``— % area INCREASE (the result is bigger).
    * ``aspect`` — % growth of the CHANGED axis = the deformation (the
      stretch only ever grows one axis; the other is unchanged).

    PIL/numpy import lazily here so importing this module stays
    stdlib-only.
    """
    from PIL import Image

    with Image.open(before) as bimg:
        bw, bh = bimg.size
        b_alpha = _alpha_of(bimg) if kind == "bg" else None
    with Image.open(after) as aimg:
        aw, ah = aimg.size
        a_alpha = _alpha_of(aimg) if kind == "bg" else None

    if kind == "bg":
        import numpy as np

        thr = JOBTEMP_REMOVED_ALPHA
        newly = int(np.logical_and(b_alpha >= thr, a_alpha < thr).sum())
        total = int(b_alpha.size)
        pct = newly / total * 100.0 if total else 0.0
    elif kind == "crop":
        before_area, after_area = bw * bh, aw * ah
        pct = (before_area - after_area) / before_area * 100.0 if before_area else 0.0
    elif kind == "upscale":
        before_area, after_area = bw * bh, aw * ah
        pct = (after_area - before_area) / before_area * 100.0 if before_area else 0.0
    elif kind == "aspect":
        # exactly one axis is stretched — measure that one's growth
        if aw != bw:
            pct = (aw - bw) / bw * 100.0 if bw else 0.0
        else:
            pct = (ah - bh) / bh * 100.0 if bh else 0.0
    else:
        raise ValueError(f"unknown tool kind: {kind}")

    return {
        "before": f"{bw}x{bh}",
        "after": f"{aw}x{ah}",
        "pct": pct,
        "label": JOB_METRIC[kind],
    }
