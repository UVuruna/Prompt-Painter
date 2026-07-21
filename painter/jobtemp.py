"""Job temp / before-after / restore — the four in-place tools' safety net.

Owner 2026-07-19: BG removal, Crop, Upscale and Aspect ratio all
overwrite files IN PLACE. Before each op the ORIGINAL is copied into a
per-job temp subdir so the dashboard can (1) show a BEFORE/AFTER viewer
and (2) RESTORE one image or the whole job. The image-generation jobs
make NEW files and never need this.

GUI rework Phase 7 (owner decision 2026-07-21) extends the SAME store
with an optional ``step`` name on ``backup``/``before_path``/
``has_backup``/``drop``: passing no step keeps the EXACT byte-for-byte
path/behavior the four standalone tools have always used (the CRITICAL
regression guard — see ``JobTemp._path_for``), while a named step (the
site-generation pipeline's BG/Crop/Aspect/Upscale stages, plus the
"original" pristine baseline and the Fixer AI's pre-fix snapshot) is
namespaced under its own subdir so per-step backups never collide with
each other or with the unnamed backup. ``restore_to``/``steps_for`` are
the new per-step query/restore API; ``restore_all``/``clear`` are
UNCHANGED in behavior — ``restore_all`` still only ever restores unnamed
backups (a named-step restore always goes through ``restore_to``
explicitly), and ``clear`` still wipes the whole job slot, named steps
included. ``JobTemp`` also tracks the cumulative bytes it has backed up
so a caller can check ``over_cap()`` against ``JOBTEMP_MAX_BYTES`` —
JobTemp itself never auto-evicts; over-cap is only a signal.

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
    JOBTEMP_MAX_BYTES,
    JOBTEMP_REMOVED_ALPHA,
    JOBTEMP_STEP_NAMES,
    JOBTEMP_STEPS_SUBDIR,
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

    Every backup is optionally tagged with a pipeline ``step`` name
    (Phase 7): the UNNAMED (``step=None``) backup keeps the exact
    on-disk path the four standalone tools have always used, while each
    NAMED step gets its own namespaced slot so a multi-step pipeline can
    back up (and later restore to) each stage independently.
    """

    def __init__(self, slot: str, folder: Path):
        self.slot = slot
        self.folder = Path(folder)
        self.root = TEMP_ROOT / slot
        # a reused slot must not inherit an old job's backups
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        # (rel, step) -> backed-up file size, in bytes — the source of
        # truth for `bytes_used`/`over_cap()`, so a repeated backup() or
        # a drop() of the same key never double-counts or drifts.
        self._sizes: dict[tuple[str, str | None], int] = {}

    def _path_for(self, rel: str, step: str | None) -> Path:
        """The on-disk backup path for ``folder/rel``.

        ``step=None`` resolves to ``root/rel`` — BYTE-FOR-BYTE the same
        location this store has always used (CRITICAL regression guard:
        the four standalone tools' on-disk layout never changes). A
        NAMED step lives under its own ``JOBTEMP_STEPS_SUBDIR/step/``
        namespace, so per-step backups can never collide with each
        other or with the unnamed backup.
        """
        if step is None:
            return self.root / rel
        return self.root / JOBTEMP_STEPS_SUBDIR / step / rel

    def backup(self, src: Path, rel: str, step: str | None = None) -> Path:
        """Copy the state of ``folder/rel`` into the temp store BEFORE
        the tool (``step=None``) or the pipeline stage named ``step``
        touches it; returns the backup path."""
        dest = self._path_for(rel, step)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        self._sizes[(rel, step)] = dest.stat().st_size
        return dest

    def drop(self, rel: str, step: str | None = None) -> None:
        """Delete a backup — for a no-op (the file was left unchanged),
        so an unchanged file holds no restore point."""
        bak = self._path_for(rel, step)
        if bak.exists():
            bak.unlink()
        self._sizes.pop((rel, step), None)

    def before_path(self, rel: str, step: str | None = None) -> Path | None:
        """The backup (BEFORE) path for ``rel``, or None if there is
        none (a no-op / never-backed-up file)."""
        bak = self._path_for(rel, step)
        return bak if bak.exists() else None

    def has_backup(self, rel: str, step: str | None = None) -> bool:
        return self._path_for(rel, step).exists()

    def steps_for(self, rel: str) -> list[str]:
        """The named steps that currently hold a backup for ``rel``, in
        PIPELINE order (``JOBTEMP_STEP_NAMES`` — see its config.py
        comment for the ordering contract this relies on): e.g. a
        per-step restore viewer's filmstrip for one image. Only steps
        that actually backed this rel up are listed; the unnamed
        (step=None) backup is never a "step" in this sense and is not
        included."""
        return [s for s in JOBTEMP_STEP_NAMES if self.has_backup(rel, step=s)]

    def restore_one(self, rel: str) -> bool:
        """Copy the UNNAMED (step=None) backup back over ``folder/rel``.
        Returns False when there is none (nothing to restore)."""
        return self._restore_from(rel, None)

    def restore_to(self, rel: str, step: str | None = None) -> bool:
        """Restore ``folder/rel`` to its state right BEFORE ``step``
        ran — copy that step's backup back over the live file.
        ``step=None`` behaves exactly like ``restore_one`` (the unnamed
        baseline). Returns False when there is no backup for that
        (rel, step) pair."""
        return self._restore_from(rel, step)

    def _restore_from(self, rel: str, step: str | None) -> bool:
        bak = self._path_for(rel, step)
        if not bak.exists():
            return False
        dest = self.folder / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bak, dest)
        return True

    def restore_all(self) -> int:
        """Restore every UNNAMED (step=None) backed-up file; returns the
        count restored. Named per-step backups (under
        ``JOBTEMP_STEPS_SUBDIR``) are NEVER touched here — a pipeline's
        "restore everything to pristine" instead calls
        ``restore_to(rel, step="original")`` per image, explicitly, so
        this method can never be accidentally widened to touch
        named-step data."""
        count = 0
        for bak in self.root.rglob("*"):
            if not bak.is_file():
                continue
            rel_parts = bak.relative_to(self.root).parts
            if rel_parts[0] == JOBTEMP_STEPS_SUBDIR:
                continue  # named-step backup — out of scope for restore_all
            rel = "/".join(rel_parts)
            if self.restore_one(rel):
                count += 1
        return count

    def clear(self) -> None:
        """Wipe this job's whole temp subdir — EVERY backup, unnamed
        and every named step alike (on panel CLOSE)."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self._sizes.clear()

    @property
    def bytes_used(self) -> int:
        """Cumulative size (bytes) of every backup this job slot
        currently holds, unnamed and named steps together."""
        return sum(self._sizes.values())

    def over_cap(self) -> bool:
        """True once this job's cumulative backup size has reached
        JOBTEMP_MAX_BYTES. JobTemp never auto-evicts on its own — this
        is only a SIGNAL; the caller decides what to do (Phase 8: stop
        taking NEW per-step backups, keep the original-only fallback,
        and raise a persistent dashboard banner)."""
        return self.bytes_used >= JOBTEMP_MAX_BYTES


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
