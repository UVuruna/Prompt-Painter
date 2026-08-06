"""Guard test - THE SPACE & LEGIBILITY LAW, static half, Tkinter (rules/GUI.md).

Adapted from rules/templates/test_layout_law.py (MIGRATE-LAYOUT.md step 1,
owner order 2026-08-06 - the design-review rollout) for a tk/ttk project: the
Qt/WPF elide and hard-size APIs do not exist here, so the banned list names
the Tk ways of freezing content out of its space.

A single line may opt out ONLY with a stated reason, written in that line's
comment as:  layout-law: exempt - <why>

The runtime half lives in `tests/test_layout_audit_tk.py` - this test catches
the CAUSES by name, that one catches the RESULT on screen.
"""

from __future__ import annotations

import re
from pathlib import Path

# --- CONFIGURATION (per project) -------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

GUI_DIRS = ("gui",)

GUI_SUFFIXES = (".py",)

SKIP_DIRS = {".git", "__pycache__", "node_modules", "build", "dist",
             "tests", ".venv", "venv"}

# Same discipline as the STRUCTURE LAW ratchet: entries only SHRINK.
RATCHET: dict[str, str] = {}

# --- THE BANNED PATTERNS (Tk edition) --------------------------------------

EXEMPT_RE = re.compile(r"layout-law:\s*exempt\s*[-—:]\s*\S")

BANNED: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(pack|grid)_propagate\s*\(\s*(False|0)\s*\)"),
     "a frozen container - its children can no longer ask for the space "
     "their content needs (Tk's equivalent of a hard size)"),
    (re.compile(r"\bwraplength\s*=\s*[1-9]\d{0,1}\b"),
     "a wraplength under 100px folds text into a sliver"),
)


def iter_gui_files() -> list[Path]:
    files: list[Path] = []
    for directory in GUI_DIRS:
        root = PROJECT_ROOT / directory
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in GUI_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def violations_in(path: Path) -> list[str]:
    found: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if EXEMPT_RE.search(line):
            continue
        for pattern, why in BANNED:
            match = pattern.search(line)
            if match:
                found.append(f"{path.relative_to(PROJECT_ROOT)}:{number}: "
                             f"{match.group(0).strip()}  <- {why}")
                break
    return found


def test_no_banned_layout_patterns() -> None:
    offenders: list[str] = []
    for path in iter_gui_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative in RATCHET:
            continue
        offenders.extend(violations_in(path))
    assert not offenders, (
        "THE SPACE & LEGIBILITY LAW (rules/GUI.md) - these lines cut content "
        "off or freeze it out of the free space:\n  "
        + "\n  ".join(offenders)
        + "\nFix in the ladder's order: (1) give the starving element the "
          "space, (2) reflow, (3) raise the window minimum, (4) scroll only "
          "when the window is genuinely full. A legitimate line opts out "
          "with `layout-law: exempt - <reason>`."
    )


def test_ratchet_entries_still_exist() -> None:
    stale = [name for name in RATCHET if not (PROJECT_ROOT / name).is_file()]
    assert not stale, ("stale RATCHET entries (file gone) - remove them: "
                       + ", ".join(stale))
