"""The sheet contract's file-name rule, skip-marker regex, and the
shared file/folder enumerators the four in-place tools and the
Collections queue use.
"""

import re

# --- The sheet contract ----------------------------------------------

# The arrow line must name a file with one of these extensions.
IMAGE_EXTENSIONS = (".png",)

# A bold span matching this marks an entry (or a whole section) as
# skipped — logged, never generated.
SKIP_MARKER_PATTERN = r"\bREUSE\b|\bSUPERSEDED\b|\bDO[\s-]+NOT[\s-]+GENERATE\b"


# --- Multi-file selection base (aspect tool, owner 2026-07-19) --------
#
# The Aspect-ratio tool picks INDIVIDUAL image FILES (a folder may hold
# mixed ratios), unlike the folder-based BG / Crop / Upscale tools. The
# job machinery keys every file by a (base folder, relative path) pair —
# JobTemp backs up under base/rel and the panel groups rows by rel's
# parent. This derives that base (the common ancestor of the picks) and
# each file's rel, so a selection spanning sub-folders still groups and
# restores correctly. Files sitting in ONE folder yield base=that folder
# and rel=filename.
def selection_base_and_rels(paths) -> tuple:
    """Return ``(base, [rel, ...])`` for a list of selected file paths:
    ``base`` is the common ancestor DIRECTORY of the picks and each
    ``rel`` is the POSIX path of the file relative to it. Raises
    ``ValueError`` on an empty selection (nothing to base)."""
    import os
    from pathlib import Path

    files = [Path(p) for p in paths]
    if not files:
        raise ValueError("empty selection — no files to base")
    if len(files) == 1:
        base = files[0].parent
    else:
        base = Path(os.path.commonpath([str(f.parent) for f in files]))
    rels = [f.relative_to(base).as_posix() for f in files]
    return base, rels


# The image extensions the four in-place tools accept — ONE home for the
# folder walk (iter_images) and the aspect file-picker filter (Rule #4/#5).
TOOL_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def iter_images(folder) -> list:
    """Every image FILE under ``folder`` (recursive), sorted — the shared
    enumerator behind the folder-based tools (BG / Crop / Upscale) and the
    Aspect tool's folder input. Non-image files are skipped."""
    from pathlib import Path

    root = Path(folder)
    return sorted(
        p for p in root.rglob("*")
        if p.suffix.lower() in TOOL_IMAGE_EXTENSIONS
    )


def iter_md_files(folder) -> list:
    """Every ``.md`` FILE under ``folder`` (recursive), sorted — mirrors
    ``iter_images``. Backs the Collections queue's "Add folder…" button:
    point it at a folder of prompt sheets and every sheet underneath,
    however nested, is queued."""
    from pathlib import Path

    root = Path(folder)
    return sorted(root.rglob("*.md"))
