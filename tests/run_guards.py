"""The guard tests' wrapper (rules/CODE.md -> Enforcement,
rules/history/2026-08-18-rework-design.md ch.8 item 2).

Wired into `.claude/settings.json`: PostToolUse runs `--fast` (structure +
config-sections + the layout law's static grep, right after every
Edit/Write) and Stop runs the full set (a session cannot end with a red
guard). The full pass runs ONLY when `changed_files.touched_anything()`
says this session changed something — "cannot tell" (import failure, no
git) always means RUN, never skip. The full pass also runs the clone guard
against this project's ratchet, the machine-readable structure ratchet
(`rules/tools/structure_guard.py` + `tests/structure_ratchet.json`, which
records LOGIC lines and lets a ratcheted file only shrink) and the
rules-size guard.

Deterministic, no app suite. Exits 2 on failure (that is what makes the
hook BLOCKING), 0 on success, prints pytest's own failure output to
stderr.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
REPO_ROOT = PROJECT_ROOT.parents[1]  # Gadgets/PromptPainter -> monorepo root

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


def _load(rel_path: str):
    """Load a monorepo-root module by path; None if it cannot be reached
    (an unreachable helper never silently disables a law — callers must
    treat None as "assume the worst / run everything")."""
    path = REPO_ROOT / rel_path
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, AttributeError, ImportError, SyntaxError):
        return None


def main(argv: list[str]) -> int:
    fast = "--fast" in argv
    changed = _load("rules/hooks/changed_files.py")
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
        return _finish(exit_code, "fast" if fast else "full")

    if fast:
        return 0

    clone_guard = _load("rules/tools/clone_guard.py")
    if clone_guard is not None:
        ratchet = TESTS_DIR / "clone_ratchet.json"
        rc = clone_guard.run([str(PROJECT_ROOT), "--ratchet", str(ratchet)])
        if rc != 0:
            print("\nGUARD FAILURE (full pass) — clone_guard found an "
                  "un-ratcheted duplicate. Fix it or extend the ratchet.",
                  file=sys.stderr)
            return 2

    structure_guard = _load("rules/tools/structure_guard.py")
    if structure_guard is not None:
        ratchet = TESTS_DIR / "structure_ratchet.json"
        problems = structure_guard.check(PROJECT_ROOT, ratchet, 1000)
        if problems:
            for line in problems:
                print(line, file=sys.stderr)
            print("\nGUARD FAILURE (full pass) — the machine-readable "
                  "structure ratchet (tests/structure_ratchet.json) is out "
                  "of date: a file went over the wall, a ratcheted file "
                  "GREW, or an entry is stale.", file=sys.stderr)
            return 2

    size_guard = _load("rules/tools/rules_size_guard.py")
    if size_guard is not None:
        rows = size_guard.check(project=PROJECT_ROOT)
        if any(not ok for _, _, _, ok, _ in rows):
            print("\nGUARD FAILURE (full pass) — a rulebook is over its "
                  "byte limit (rules_size_guard).", file=sys.stderr)
            return 2

    return 0


def _finish(code: int, label: str) -> int:
    print(
        f"\nGUARD FAILURE ({label} pass) — fix the violation above "
        "before continuing.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
