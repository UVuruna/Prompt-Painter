"""THE DOCS LAW's navigation guard (rules/DOCS.md -> Navigation Chain +
Enforcement) — the full chain from ``README.md`` must reach EVERY
project ``.md`` file, and no relative markdown link may point at a
file that does not exist.

``tests/fixtures/*.md`` are exempt from the REACHABILITY check only:
they are synthetic prompt-SHEET data feeding the sheet-parser tests
(fixture content, not documentation) and were never part of the docs
navigation chain — see ``tests/___tests.md``. They are still checked
for broken outbound links like every other ``.md`` file.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    "build", "dist", "tools", "chrome-profile", "__pycache__", "out",
    ".git", "UV", "venv", ".venv", ".pytest_cache",
}

# "sheets/" is config.SHEETS_DIR — where the New Collection (AI) wizard
# SAVES the owner's generated prompt sheets. Those .md files are product
# CONTENT, not project documentation: they are never linked from README
# (they come and go with every run), so the navigation chain has nothing
# to say about them. Governing them made THE DOCS LAW fail the moment
# the wizard produced its first sheet — a guard failure with no doc to
# fix (owner 2026-08-04).
REACHABILITY_EXEMPT_DIRS = {"tests/fixtures", "sheets/"}

LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _all_md_files() -> list[Path]:
    files = []
    for path in PROJECT_ROOT.rglob("*.md"):
        rel = path.relative_to(PROJECT_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def _link_targets(path: Path) -> list[str]:
    """Every relative link target in the file — external URLs,
    mailto:, and pure same-file anchors (#foo) are not project doc
    links, so they are excluded here."""
    text = path.read_text(encoding="utf-8", errors="replace")
    targets = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith("#"):
            continue
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _resolve(path: Path, target: str) -> Path:
    return (path.parent / target).resolve()


def test_every_relative_md_link_resolves_to_a_real_file():
    broken: list[str] = []
    for path in _all_md_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        for target in _link_targets(path):
            resolved = _resolve(path, target)
            if not resolved.exists():
                broken.append(f"{rel} -> {target}")
    assert not broken, (
        f"THE DOCS LAW: broken relative .md link(s): {broken}"
    )


def test_every_project_md_is_reachable_from_readme():
    readme = PROJECT_ROOT / "README.md"
    assert readme.is_file(), "project root must have a README.md"

    all_md = {p.resolve() for p in _all_md_files()}
    exempt = {
        p.resolve() for p in _all_md_files()
        if any(
            skip in p.relative_to(PROJECT_ROOT).as_posix()
            for skip in REACHABILITY_EXEMPT_DIRS
        )
    }
    governed = all_md - exempt

    visited: set[Path] = set()
    stack = [readme.resolve()]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for target in _link_targets(Path(current)):
            resolved = _resolve(Path(current), target)
            if resolved.suffix == ".md" and resolved.exists():
                resolved = resolved.resolve()
                if resolved not in visited:
                    stack.append(resolved)

    unreachable = governed - visited
    assert not unreachable, (
        "THE DOCS LAW: .md file(s) unreachable from README.md (broken"
        " navigation chain): "
        f"{sorted(p.relative_to(PROJECT_ROOT).as_posix() for p in unreachable)}"
    )
