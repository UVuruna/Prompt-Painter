"""The four guard tests' fast wrapper (rules/CODE.md -> Enforcement).

Wired into `.claude/settings.json`: PostToolUse runs `--fast` (structure
+ config-sections only, right after every Edit/Write) and Stop runs the
full set (all four guards — a session cannot end with a red guard).

Deterministic, no app suite, stays under ~2s so it never slows down a
normal edit loop. Exits 2 on failure (that is what makes the hook
BLOCKING), 0 on success, prints pytest's own failure output to stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

FAST_GUARDS = [
    "test_structure_law.py",
    "test_config_sections.py",
]
ALL_GUARDS = FAST_GUARDS + [
    "test_docs_coverage.py",
    "test_doc_links.py",
]


def main(argv: list[str]) -> int:
    fast = "--fast" in argv
    guards = FAST_GUARDS if fast else ALL_GUARDS
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
