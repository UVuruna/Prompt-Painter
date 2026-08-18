"""THE DOCS LAW's coverage guard (rules/DOCS.md -> Tiers + Enforcement)
— every source file has the docs its TIER requires:

| Tier | Obligation |
|------|-----------|
| Trivial (glue/re-export/plain wiring) | none — a one-line mention in the folder's ``___folder.md`` is enough |
| Standard (ordinary module) | ``__about/{name}.md`` |
| Algorithmic (real algorithm, GUI widget, config/data table, protocol) | ``__about/{name}.md`` **and** ``__flow/{name}.md`` |
| ``tests/`` (any file under the tests folder) | none per-file — ``tests/___tests.md`` alone |

The tier lists below were seeded 2026-08-01 during the MD-First 2.0
migration (folder-by-folder __about/__flow split of every `gui/`,
`painter/`, `painter/ai/`, `painter/config/` and `setup/` file).
Changing a file's tier — or adding/removing a source file — means
updating the matching list HERE, in the SAME commit (rules/DOCS.md).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    "build", "dist", "tools", "chrome-profile", "__pycache__",
    # everything the program GENERATES (config.GENERATED_ROOT,
    # owner 2026-08-04) plus the pre-move locations
    "output", "out", "sheets",
    ".git", "UV", "venv", ".venv",
    # harness state, not product code (test_doc_links.py skips it too) —
    # .claude/uv_windows.py is the F3 `uv shot` window registry, governed
    # by rules/howto/runner.md, not THE DOCS LAW's per-file tier system
    ".claude",
}

# Every folder that holds governed source code and therefore needs its
# own ___folder.md entry point (root uses README.md instead — exempt).
CODE_FOLDERS = [
    "gui",
    "gui/tool_panels",
    "painter",
    "painter/ai",
    "painter/config",
    "setup",
    "tests",
]

# Trivial tier: glue / re-export / plain wiring, no __about of its own —
# a one-line mention in the folder's ___folder.md is the whole obligation.
TRIVIAL_FILES: set[str] = {
    "painter/__init__.py",
    "gui/app.py",
    "gui/tool_panels/__init__.py",
}

# Algorithmic tier: real algorithm / GUI widget / config-data table /
# protocol — needs BOTH __about/{name}.md and __flow/{name}.md. Every
# other non-Trivial, non-test file defaults to Standard (__about only).
FLOW_REQUIRED_FILES: set[str] = {
    # gui/ — GUI windows/widgets and the PainterGui mixins
    "gui/app_build.py", "gui/app_views.py", "gui/app_jobs.py",
    "gui/app_checker_fixer.py", "gui/app_tools.py", "gui/app_settings.py",
    "gui/agent_panel.py", "gui/api_panel.py", "gui/widgets.py",
    "gui/icons.py", "gui/theme.py", "gui/scroll.py", "gui/switch.py",
    "gui/filter_editor.py", "gui/aspect_canvas.py", "gui/logic.py",
    "gui/dash_panels.py", "gui/tool_dash.py", "gui/menu.py",
    "gui/select_window.py", "gui/doc_window.py", "gui/restore_windows.py",
    "gui/image_viewer.py", "gui/dialogs.py",
    # gui/tool_panels/ — the standalone-tool panel widgets
    "gui/tool_panels/base.py", "gui/tool_panels/bg.py",
    "gui/tool_panels/geometry.py", "gui/tool_panels/image_checker.py",
    # painter/ — the engine's real algorithms/protocols
    "painter/chrome.py", "painter/driver.py", "painter/runner.py",
    "painter/recovery.py",
    "painter/sheet_parser.py", "painter/bg_remove.py",
    "painter/postprocess.py", "painter/upscale.py", "painter/aspect.py",
    "painter/filters.py", "painter/jobtemp.py",
    # painter/ai/ — the AI client/sheet-flow/checker protocols
    "painter/ai/client.py", "painter/ai/sheet_flow.py",
    "painter/ai/checks.py",
    # painter/config/ — every config/data-table module
    "painter/config/paths.py", "painter/config/sheet.py",
    "painter/config/upscale.py", "painter/config/aspect.py",
    "painter/config/postprocess.py", "painter/config/theme.py",
    "painter/config/jobs.py", "painter/config/jobtemp.py",
    "painter/config/sites.py", "painter/config/ai.py",
    # setup/ — the build pipeline's real algorithms
    "setup/build.py", "setup/svg_to_ico.py",
    # root
    "main.py",
}


def _source_files() -> list[Path]:
    files = []
    for path in PROJECT_ROOT.rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def _is_test_file(rel_posix: str) -> bool:
    return rel_posix == "tests" or rel_posix.startswith("tests/")


def test_tier_lists_name_real_files():
    """A guard whose lists have drifted from disk passes for the wrong
    reason — pin every named file actually exists."""
    missing = [
        rel for rel in (TRIVIAL_FILES | FLOW_REQUIRED_FILES)
        if not (PROJECT_ROOT / rel).is_file()
    ]
    assert not missing, f"Tier list names non-existent file(s): {missing}"
    overlap = TRIVIAL_FILES & FLOW_REQUIRED_FILES
    assert not overlap, f"File(s) listed as BOTH Trivial and Algorithmic: {overlap}"


def test_every_code_folder_has_a_folder_doc():
    missing = [
        folder for folder in CODE_FOLDERS
        if not (PROJECT_ROOT / folder / f"___{Path(folder).name}.md").is_file()
    ]
    assert not missing, (
        f"Code folder(s) missing their ___folder.md entry point: {missing}"
    )


def test_every_source_file_has_the_docs_its_tier_requires():
    missing_about: list[str] = []
    missing_flow: list[str] = []
    unlisted_but_undocumented: list[str] = []

    for path in _source_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if _is_test_file(rel):
            continue  # tests/ tier: ___tests.md alone, no per-file docs
        if rel in TRIVIAL_FILES:
            continue  # Trivial tier: no __about of its own

        about = path.parent / "__about" / f"{path.stem}.md"
        if not about.is_file():
            missing_about.append(rel)

        if rel in FLOW_REQUIRED_FILES:
            flow = path.parent / "__flow" / f"{path.stem}.md"
            if not flow.is_file():
                missing_flow.append(rel)

    assert not missing_about, (
        "THE DOCS LAW: source file(s) missing their __about/{name}.md"
        f" (Standard or Algorithmic tier, per rules/DOCS.md): {missing_about}"
    )
    assert not missing_flow, (
        "THE DOCS LAW: Algorithmic-tier source file(s) missing their"
        f" __flow/{{name}}.md: {missing_flow}"
    )


def test_tests_folder_has_no_stray_per_file_docs():
    """The tests/ tier is FOLDER-doc only — a __about/ or __flow/
    subfolder under tests/ would mean someone tried to give a test
    module its own file docs, against the tier rule."""
    stray = [
        d for name in ("__about", "__flow")
        if (d := PROJECT_ROOT / "tests" / name).is_dir()
    ]
    assert not stray, (
        f"tests/ must not carry per-file docs (tier = folder-doc only): {stray}"
    )
