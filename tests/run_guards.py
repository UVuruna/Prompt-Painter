"""The four guard tests' fast wrapper (rules/CODE.md -> Enforcement).

Wired into `.claude/settings.json`: PostToolUse runs `--fast` (structure
+ config-sections only, right after every Edit/Write) and Stop runs the
full set (all four guards — a session cannot end with a red guard).

Deterministic, no app suite, stays under ~2s so it never slows down a
normal edit loop. Exits 2 on failure (that is what makes the hook
BLOCKING), 0 on success, prints pytest's own failure output to stderr.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent

CODE_FAST_GUARDS = [
    "test_structure_law.py",
    "test_config_sections.py",
]
CODE_FULL_GUARDS = [
    "test_docs_coverage.py",
    "test_doc_links.py",
]
# THE SPACE & LEGIBILITY LAW + Zubi v2 - these RUN ONLY WHEN A GUI FILE
# WAS CHANGED (owner decree 2026-08-14, root CLAUDE.md -> The Laws #7):
# the runtime ones build real windows off-screen and measure them, so
# firing them at the end of a turn that touched no GUI file spends
# minutes to prove something nobody put at risk.
GUI_FAST_GUARDS = [
    # the static half - a banned-API grep over the GUI sources
    "test_layout_law.py",
]
GUI_FULL_GUARDS = [
    # the runtime half - builds the real window off-screen and measures it
    "test_layout_audit_tk.py",
    # Zubi v2 Tk (owner's order 2026-08-11): ALG-5/6/7 over the same
    # registry + the long-refusal ImageViewer fixture, with its own
    # planted-violation self-test
    "test_layout_zubi_tk.py",
]


def _changed():
    """The monorepo's one authority on what this session touched.

    `rules/hooks/changed_files.py`, loaded by path so every project
    answers the question identically. None when it cannot be loaded —
    callers then run every guard: an unreachable helper never silently
    disables a law.
    """
    helper = PROJECT_ROOT.parents[1] / "rules" / "hooks" / "changed_files.py"
    try:
        spec = importlib.util.spec_from_file_location("uv_changed", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, AttributeError, ImportError, SyntaxError):
        return None
    return module


def main(argv: list[str]) -> int:
    fast = "--fast" in argv
    changed = _changed()
    if not fast and changed is not None and not changed.touched_anything(
        PROJECT_ROOT
    ):
        print("guards: session changed no file — full pass skipped")
        return 0
    gui_changed = changed is None or changed.touched_gui(PROJECT_ROOT)
    guards = list(CODE_FAST_GUARDS)
    if not fast:
        guards += CODE_FULL_GUARDS
    if gui_changed:
        guards += GUI_FAST_GUARDS
        if not fast:
            guards += GUI_FULL_GUARDS
    else:
        print("guards: no GUI file changed — layout/Zubi guards skipped")
    targets = [str(TESTS_DIR / name) for name in guards]

    exit_code = pytest.main(["-q", "--no-header", *targets])
    if exit_code != 0:
        print(
            f"\nGUARD FAILURE ({'fast' if fast else 'full'} pass) —"
            " fix the violation above before continuing.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
