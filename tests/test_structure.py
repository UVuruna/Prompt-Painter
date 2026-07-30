"""THE STRUCTURE LAW's guard (root CLAUDE.md Rule #20, owner decree
2026-07-29) — the test that makes "no god-files" hold by FAILING the
build instead of being noticed and tolerated.

The law's own history is the reason it exists: this project's
``gui.py`` reached 8,800+ lines while every session agreed it should
be split. A written rule with no failing test held nothing.

**The ratchet.** Every source file over ``MAX_LINES`` must be listed in
``RATCHET`` with WHY it is still whole and which session owes the fix.
The list may only SHRINK: an entry is deleted when its file is split,
and a NEW entry may be added ONLY with the owner's explicit approval in
that same session (Rule #20 point 3). A file that outgrows the limit
without an entry fails this test, loudly, naming the file.

A RATCHET entry whose file has SINCE been split (or deleted) also
fails — a stale allowance is exactly how a ratchet quietly loosens.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Rule #20's own thresholds: <=500 normal, 500-1000 a smell that forces
# the "does this file have more than one responsibility?" question,
# >1000 a VIOLATION that splits or documents why it cannot.
MAX_LINES = 1000

# directories that hold no source of ours (build output, vendored
# binaries, the automation browser profile, caches)
SKIP_DIRS = {
    "build", "dist", "tools", "chrome-profile", "__pycache__", "out",
    ".git", "UV", "venv", ".venv",
}

# path (POSIX, project-relative) -> why it is still one file + who owes
# the split. SHRINK ONLY — see this module's docstring.
RATCHET: dict[str, str] = {
    "gui/app_jobs.py": (
        "SiteJobsMixin — the site run loop, the API-image job and the"
        " dashboard event dispatch in one mixin. Second-round split"
        " (owner approved the three worst first, 2026-07-30):"
        " app_jobs.py + an api-image job module + the dispatch table."
    ),
    "painter/driver.py": (
        "SiteDriver — Chrome attach/launch, the composer protocol, the"
        " turn-based done edge, image extraction and the image-failed"
        " recovery ladder. Second-round split (owner approved the three"
        " worst first, 2026-07-30)."
    ),
    "gui/agent_panel.py": (
        "AgentPanel — ONE cohesive responsibility (one site's control"
        " surface) whose sub-panel builders make it long. Second-round"
        " candidate (owner approved the three worst first,"
        " 2026-07-30): the UI-SKETCH sub-panel builders could move to"
        " their own module, or this documents itself as irreducible."
    ),
    "tests/test_gui_tool_panels.py": (
        "The standalone-tool settings panels' whole suite. Splits WITH"
        " gui/tool_panels.py's own package split — one test module per"
        " panel module (owner approved, 2026-07-30, second round)."
    ),
    "tests/test_runner.py": (
        "The run-loop suite (F1 turn protocol, refusals, quota, the"
        " recovery ladder, reports). Second-round split by concern."
    ),
    "tests/test_ai.py": (
        "The AI suite (client/transport, sheet flow, checks, flags)."
        " Splits WITH painter/ai.py's own package split — one test"
        " module per package module (owner approved, 2026-07-30)."
    ),
    "tests/test_driver.py": (
        "The CDP-driver suite. Splits WITH painter/driver.py in the"
        " second round."
    ),
    "tests/test_gui_fixer.py": (
        "The Fixer-AI suite (panel wiring, decision table, auto-"
        " dispatch, manual buttons). Second-round split by concern."
    ),
}


def _source_files() -> list[Path]:
    """Every .py file that is OURS — the whole project tree minus the
    build output, vendored binaries and caches (SKIP_DIRS)."""
    files = []
    for path in PROJECT_ROOT.rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def test_no_unlisted_god_files():
    """Rule #20: a file over MAX_LINES either splits or is a documented
    RATCHET entry. Anything else fails the build."""
    offenders = {}
    for path in _source_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel in RATCHET:
            continue
        lines = _line_count(path)
        if lines > MAX_LINES:
            offenders[rel] = lines
    assert not offenders, (
        "God-file(s) over "
        f"{MAX_LINES} lines with no RATCHET entry: {offenders}. Split by"
        " RESPONSIBILITY (root CLAUDE.md Rule #20) — or, with the"
        " owner's explicit approval in THIS session, add a RATCHET entry"
        " saying why it must stay whole and who owes the split."
    )


def test_ratchet_entries_are_all_still_needed():
    """A stale allowance is how a ratchet quietly loosens: once a listed
    file is split (or deleted), its entry must go."""
    stale = {}
    for rel, _why in RATCHET.items():
        path = PROJECT_ROOT / rel
        if not path.exists():
            stale[rel] = "file is gone"
        elif _line_count(path) <= MAX_LINES:
            stale[rel] = f"now {_line_count(path)} lines — under the limit"
    assert not stale, (
        f"RATCHET entries no longer needed: {stale}. Delete them — the"
        " list may only shrink."
    )


def test_every_ratchet_entry_names_its_reason():
    """An entry is an owner-approved DEBT, not a silent exemption: it
    must say why the file is whole and who owes the split."""
    empty = [rel for rel, why in RATCHET.items() if len(why.strip()) < 40]
    assert not empty, (
        f"RATCHET entries without a real reason: {empty}. Each must"
        " document WHY the file stays whole and which session owes the"
        " fix (Rule #20 point 3)."
    )
