"""THE CONFIG SECTION LAW's guard (rules/CODE.md -> THE CONFIG SECTION
LAW, owner decree 2026-08-01) — config/data files are STRUCTURES, not
notebooks: every table/class/constant is defined ONCE, complete, under
a named section banner; a variant patched in later, far from its
family (``TABLE["x"]["y"] = ...`` below the table, ``.update(...)`` at
module level, or an entry dumped at file end) is a defect this test
catches mechanically.

``CONFIG_FILES`` seeded 2026-08-01 (MIGRATE-DOCS session) with every
``painter/config/*.py`` data/config module — the project's ONE home
for tunables (root Rule #4). Each was given section-banner COMMENTS
in the same session (zero behavior change) — see each file's
``__about``/``__flow`` docs for its section list.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

BANNER_RE = re.compile(r"^#\s*═{3,}")

# path (POSIX, project-relative) -> every config/data file this law
# governs. Grows when a new config/data module is born; a module that
# stops being config/data (rare) leaves the list in the same session.
CONFIG_FILES: list[str] = [
    "painter/config/formatters.py",
    "painter/config/paths.py",
    "painter/config/sheet.py",
    "painter/config/upscale.py",
    "painter/config/aspect.py",
    "painter/config/postprocess.py",
    "painter/config/theme.py",
    "painter/config/jobs.py",
    "painter/config/jobtemp.py",
    "painter/config/sites.py",
    "painter/config/ai.py",
]

# definitions/assignments outside a section banner ARE reported for
# these node types; imports and the module docstring are exempt (they
# are not "table" content the law governs).
_DEFINITION_NODES = (ast.Assign, ast.AnnAssign, ast.ClassDef, ast.FunctionDef)


def _source_and_tree(path: Path) -> tuple[str, ast.Module]:
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path))


def _banner_lines(source: str) -> list[int]:
    return [
        i + 1 for i, line in enumerate(source.splitlines())
        if BANNER_RE.match(line)
    ]


def _subscript_root_name(node: ast.expr) -> str:
    """Walk a (possibly chained) Subscript/Attribute target down to its
    root Name — ``TABLE["x"]["y"]`` -> ``"TABLE"``."""
    while isinstance(node, (ast.Subscript, ast.Attribute)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else "<expr>"


def test_config_files_resolve_and_are_not_empty():
    """A guard that walks nothing passes forever — pin that CONFIG_FILES
    names real files."""
    assert CONFIG_FILES, "CONFIG_FILES must not be empty"
    missing = [
        rel for rel in CONFIG_FILES if not (PROJECT_ROOT / rel).is_file()
    ]
    assert not missing, f"CONFIG_FILES names non-existent file(s): {missing}"


def test_every_top_level_definition_sits_under_a_banner():
    """No top-level table/class/constant may sit BEFORE the file's first
    section banner (imports and the module docstring are exempt) — a
    file with definitions and zero banners fails too."""
    problems: dict[str, str] = {}
    for rel in CONFIG_FILES:
        path = PROJECT_ROOT / rel
        source, tree = _source_and_tree(path)
        banners = _banner_lines(source)
        definitions = [
            node for node in tree.body if isinstance(node, _DEFINITION_NODES)
        ]
        if not definitions:
            continue
        if not banners:
            problems[rel] = "has top-level definitions but ZERO section banners"
            continue
        first_banner = min(banners)
        orphans = [
            f"line {node.lineno}" for node in definitions
            if node.lineno < first_banner
        ]
        if orphans:
            problems[rel] = f"definition(s) before the first banner: {orphans}"
    assert not problems, (
        "THE CONFIG SECTION LAW: top-level definitions outside any"
        f" section banner: {problems}. Give the file's opening block a"
        " banner, or move the orphaned definition under its section."
    )


def test_no_post_definition_patching():
    """``TABLE["x"] = ...`` / ``TABLE.update(...)`` / ``TABLE.setdefault
    (...)`` at MODULE level is the canonical forbidden pattern — a
    variant patched in far from its family instead of edited into the
    table's own literal, in its own section."""
    problems: dict[str, list[str]] = {}
    for rel in CONFIG_FILES:
        path = PROJECT_ROOT / rel
        _source, tree = _source_and_tree(path)
        offenders: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        name = _subscript_root_name(target)
                        offenders.append(
                            f"line {node.lineno}: {name}[...] = ... (post-definition patch)"
                        )
            elif isinstance(node, ast.AugAssign) and isinstance(
                node.target, ast.Subscript
            ):
                name = _subscript_root_name(node.target)
                offenders.append(
                    f"line {node.lineno}: {name}[...] {'<op>='} ... (post-definition patch)"
                )
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("update", "setdefault")
                    and isinstance(call.func.value, ast.Name)
                ):
                    offenders.append(
                        f"line {node.lineno}: {call.func.value.id}.{call.func.attr}(...) (post-definition patch)"
                    )
        if offenders:
            problems[rel] = offenders
    assert not problems, (
        "THE CONFIG SECTION LAW: module-level post-definition patching"
        f" found: {problems}. Edit the EXISTING structure in place,"
        " inside its own section — never patch a table from outside it."
    )


def test_no_duplicate_dict_keys():
    """A duplicate literal key in any dict silently shadows the earlier
    one — usually the sign of a copy-pasted entry that forgot to change
    its key, the exact drift THE CONFIG SECTION LAW exists to catch."""
    problems: dict[str, list[str]] = {}
    for rel in CONFIG_FILES:
        path = PROJECT_ROOT / rel
        _source, tree = _source_and_tree(path)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen: set = set()
            for key in node.keys:
                if key is None or not isinstance(key, ast.Constant):
                    continue  # a **spread or a non-literal key — skip
                if not isinstance(key.value, (str, int, float, bool, bytes)):
                    continue
                if key.value in seen:
                    offenders.append(
                        f"line {node.lineno}: duplicate key {key.value!r}"
                    )
                seen.add(key.value)
        if offenders:
            problems[rel] = offenders
    assert not problems, (
        f"THE CONFIG SECTION LAW: duplicate dict key(s) found: {problems}."
        " A duplicate key silently shadows the earlier entry — fix the"
        " copy-paste."
    )
