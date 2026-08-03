"""``PromptImageSection`` (faza 2, owner 2026-08-03 — UV tačka 3): the
PROMPT + IMAGE mode's setup surface. Pure-ish widget tests: the section
parses the queued sheets and reports per-entry eligibility against the
SAME resolution the runner uses (``resolve_input_images`` — sheet
folder → Reference folder → absolute); the real narrowing at Start is
``run_sheet(require_input_image=True)``, tested in
test_runner_images.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import gui


@pytest.fixture
def root(tk_root):
    return tk_root

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n" + bytes.fromhex(
        "0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da6364f8cfc0000000050001"
        "0d0a2db40000000049454e44ae426082"
    )
)


def _write_sheet(folder: Path) -> Path:
    (folder / "refs").mkdir(parents=True, exist_ok=True)
    (folder / "refs" / "hero.png").write_bytes(PNG_1PX)
    sheet = folder / "collection.md"
    sheet.write_text(
        "# T\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `refs/hero.png`\n\n"
        "```\np0\n```\n\n"
        "**NoRef** → `assets/x/NoRef.png`\n\n"
        "```\np1\n```\n\n"
        "**Missing** → `assets/x/Missing.png`\n"
        "← `refs/gone.png`\n\n"
        "```\np2\n```\n",
        encoding="utf-8",
    )
    return sheet


def _make_section(root, sheets):
    return gui.PromptImageSection(root, get_sheet_paths=lambda: sheets)


def test_refresh_reports_complete_missing_and_no_ref(root, tmp_path):
    sheet = _write_sheet(tmp_path)
    section = _make_section(root, [sheet])
    section.refresh()
    lines = section.status_list.get(0, "end")
    assert any(ln.startswith("  ✔ Hero") for ln in lines)
    assert any(ln.startswith("  — NoRef") for ln in lines)
    assert any("✖ Missing" in ln and "refs/gone.png" in ln for ln in lines)
    assert section.summary_var.get() == (
        "3 prompt(s) · 1 complete pair(s) → 1 will run"
    )


def test_reference_folder_fallback_completes_a_far_ref(root, tmp_path):
    """A ref not beside the sheet resolves through the section's
    Reference folder — the second rung, same as the runner's."""
    sheet_dir = tmp_path / "sheets"
    sheet_dir.mkdir()
    sheet = sheet_dir / "s.md"
    sheet.write_text(
        "# T\n\n**Yoda** → `assets/x/Yoda.png`\n"
        "← `sw_reference/Yoda.png`\n\n```\np\n```\n",
        encoding="utf-8",
    )
    stash = tmp_path / "stash"
    (stash / "sw_reference").mkdir(parents=True)
    (stash / "sw_reference" / "Yoda.png").write_bytes(PNG_1PX)
    section = _make_section(root, [sheet])
    section.refresh()
    assert "0 complete" in section.summary_var.get().replace(
        "0 complete pair(s)", "0 complete"
    )
    section.ref_dir_var.set(str(stash))
    section.refresh()
    assert section.summary_var.get() == (
        "1 prompt(s) · 1 complete pair(s) → 1 will run"
    )


def test_a_set_but_nonexistent_reference_folder_is_flagged(root, tmp_path):
    sheet = _write_sheet(tmp_path)
    section = _make_section(root, [sheet])
    section.ref_dir_var.set(str(tmp_path / "nope"))
    section.refresh()
    lines = section.status_list.get(0, "end")
    assert any(ln.startswith("⚠ Reference folder not found") for ln in lines)


def test_settings_round_trip(root):
    section = _make_section(root, [])
    section.enabled_var.set(True)
    section.ref_dir_var.set("U:/refs")
    stored = section.get_settings()
    fresh = _make_section(root, [])
    fresh.apply_settings(stored)
    assert fresh.enabled() is True
    assert fresh.ref_dir_var.get() == "U:/refs"


def test_reference_dir_none_while_blank(root):
    section = _make_section(root, [])
    assert section.reference_dir() is None
    section.ref_dir_var.set("  ")
    assert section.reference_dir() is None
