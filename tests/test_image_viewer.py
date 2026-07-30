"""``ImageViewer`` — the per-image dashboard viewer (GUI rework Phase
F4f, owner G6/G7). Constructed directly against a small in-memory
``entries`` list (the same shape ``SettingsMixin._image_viewer_entries``
builds — title/drop_path/rel/dest/prompt/refused_reason), never through
a real ``PainterGui``/``DashPanel`` — mirrors this suite's own "pure
helpers + fakes over real Tk widgets" convention (``___tests.md``).

Imported directly from ``gui.viewers`` (not via ``import gui; gui.
ImageViewer(...)``) — ``ImageViewer`` is NOT YET re-exported by
``gui/__init__.py`` (out of this session's edit scope: that file is
mid-edit by a parallel session on an unrelated phase — see
``gui/viewers.md``'s Design Decisions for the note). Every OTHER test
file in this suite reaches viewers through the ``gui.X`` re-export so
``monkeypatch.setattr(gui, "X", fake)`` keeps working across a future
module move; ``ImageViewer`` has no such caller-side monkeypatch need
yet, so the direct import is harmless today and should be revisited
(added to ``gui/__init__.py``'s re-export block) once that file is free.

``winfo_manager()`` (packed/`""`), not ``winfo_ismapped()``, proves a
child is shown/hidden — the shared session root is withdrawn (never
mapped), so ``winfo_ismapped()`` is 0 for every descendant regardless of
its own pack state (the SAME convention ``test_gui_running_view.py``/
``test_gui_pipeline.py`` already use for exactly this reason).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import pytest
from PIL import Image

from gui.image_viewer import ImageViewer


@pytest.fixture
def root(tk_root):
    return tk_root


def make_png(path: Path) -> None:
    """A tiny REAL PNG, fully decodable by PIL. NOTE — deviation from
    the ``PNG_1PX`` raw-hex-bytes pattern ``test_runner.py`` uses: those
    bytes sniff as PNG and expose header dimensions, but do NOT survive
    a full ``Image.load()`` (broken IDAT stream on the Pillow version
    this repo pins — confirmed by hand). ``ImageViewer`` calls the real
    ``_scaled_photo`` path (``Image.open().load()``, same as DocWindow's
    own image section), which needs an actually decodable file, so this
    follows ``test_viewer.py``'s own ``make_png`` convention
    (``Image.new(...).save(path, 'PNG')``) instead."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(path, "PNG")


def make_entries(tmp_path: Path) -> list[dict]:
    """Three entries: a saved image, a refused (no file) one, and a
    second saved image — enough to exercise Prev/Next disabling at BOTH
    ends around a middle 'no file' entry."""
    dest0 = tmp_path / "Glory_gem.png"
    make_png(dest0)
    dest2 = tmp_path / "Zeus_v2_gem.png"
    make_png(dest2)
    return [
        {
            "title": "Glory", "drop_path": "assets/emblem/mood/Glory.png",
            "rel": "emblem/mood/Glory_gem.png", "dest": dest0,
            "prompt": "a golden glory emblem", "refused_reason": None,
        },
        {
            "title": "Hera", "drop_path": "assets/emblem/mood/Hera.png",
            "rel": None, "dest": None, "prompt": "a hera emblem",
            "refused_reason": "No saved file — refused, skipped, or not"
            " generated yet.",
        },
        {
            "title": "Zeus", "drop_path": "assets/emblem/mood/Zeus.png",
            "rel": "emblem/mood/Zeus_v2_gem.png", "dest": dest2,
            "prompt": "a zeus emblem", "refused_reason": None,
        },
    ]


# --- title = the saved file's stem, never the full drop path ----------


def test_title_shows_the_saved_files_stem(root, tmp_path):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 0)
    assert viewer._title_var.get() == "Glory_gem"
    assert viewer.title() == "Glory_gem"
    viewer.destroy()


def test_title_falls_back_to_the_drop_paths_stem_with_no_saved_file(
    root, tmp_path,
):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 1)
    assert viewer._title_var.get() == "Hera"
    viewer.destroy()


def test_title_shows_a_versioned_stem_unchanged(root, tmp_path):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 2)
    assert viewer._title_var.get() == "Zeus_v2_gem"
    viewer.destroy()


# --- Prev/Next navigate the whole list in ONE window, disable at ends -


def test_prev_next_navigate_and_disable_at_ends(root, tmp_path):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 0)
    assert viewer._prev_btn.cget("state") == "disabled"
    assert viewer._next_btn.cget("state") == "normal"

    viewer._go_next()
    assert viewer._index == 1
    assert viewer._prev_btn.cget("state") == "normal"
    assert viewer._next_btn.cget("state") == "normal"

    viewer._go_next()
    assert viewer._index == 2
    assert viewer._next_btn.cget("state") == "disabled"

    # no wraparound — Next at the last entry is a no-op
    viewer._go_next()
    assert viewer._index == 2

    viewer._go_prev()
    assert viewer._index == 1
    viewer.destroy()


# --- a refused/missing entry shows its reason where the image would be


def test_refused_entry_shows_the_reason_text_in_place_of_the_image(
    root, tmp_path,
):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 1)
    assert viewer._image_label.cget("text") == entries[1]["refused_reason"]
    assert viewer._image_label.cget("image") == ""
    # nothing on disk for this entry — Delete has nothing to target
    assert viewer._delete_btn.cget("state") == "disabled"
    viewer.destroy()


def test_entry_with_a_saved_file_shows_no_placeholder_text(root, tmp_path):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 0)
    assert viewer._image_label.cget("text") == ""
    assert viewer._image_label.cget("image") != ""
    assert viewer._delete_btn.cget("state") == "normal"
    viewer.destroy()


# --- Check / Steps: absent with no lookup, present when one applies ---


def test_check_and_steps_sections_absent_without_lookups(root, tmp_path):
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 0)
    assert viewer._check_btn.winfo_manager() == ""
    assert viewer._steps_btn.winfo_manager() == ""
    viewer.destroy()


def test_check_section_present_only_for_the_entry_the_lookup_matches(
    root, tmp_path,
):
    entries = make_entries(tmp_path)

    def check_lookup(drop_path):
        if drop_path != entries[0]["drop_path"]:
            return None
        return {"rel": entries[0]["rel"], "defects": ["blurry edge"],
                "raw": "full vision-model report"}

    viewer = ImageViewer(root, entries, 0, check_lookup=check_lookup)
    assert viewer._check_btn.winfo_manager() == "pack"
    report = viewer._check_txt.get("1.0", "end")
    assert "blurry edge" in report
    assert "full vision-model report" in report

    viewer._go_next()  # Hera — check_lookup returns None for it
    assert viewer._check_btn.winfo_manager() == ""
    viewer.destroy()


def test_steps_section_present_only_for_the_entry_the_lookup_matches(
    root, tmp_path,
):
    entries = make_entries(tmp_path)
    stage_path = tmp_path / "stage_original.png"
    make_png(stage_path)

    def steps_lookup(rel):
        return [("Original", stage_path)] if rel == entries[0]["rel"] else []

    viewer = ImageViewer(root, entries, 0, steps_lookup=steps_lookup)
    assert viewer._steps_btn.winfo_manager() == "pack"
    assert viewer._steps_btn.cget("text") == "▶  Steps (1)"

    viewer._go_next()  # Hera has no rel at all -> steps_lookup never runs
    assert viewer._steps_btn.winfo_manager() == ""
    viewer.destroy()


def test_clicking_a_step_thumbnail_swaps_the_main_view_then_back(
    root, tmp_path,
):
    entries = make_entries(tmp_path)
    stage_path = tmp_path / "stage_original.png"
    make_png(stage_path)
    steps_lookup = lambda rel: (
        [("Original", stage_path)] if rel == entries[0]["rel"] else []
    )
    viewer = ImageViewer(root, entries, 0, steps_lookup=steps_lookup)

    viewer._view_step_thumb("Original", stage_path)
    assert viewer._view_step == ("Original", stage_path)
    assert viewer._step_note_var.get() == "viewing: Original"
    assert viewer._back_btn.winfo_manager() == "pack"

    viewer._clear_step_view()
    assert viewer._view_step is None
    assert viewer._back_btn.winfo_manager() == ""
    viewer.destroy()


def test_restore_to_this_step_calls_restore_cb_and_on_restored(
    root, tmp_path,
):
    entries = make_entries(tmp_path)
    calls = []

    def restore_cb(rel, label):
        calls.append((rel, label))
        return True

    restored = []
    steps_lookup = lambda rel: (
        [("Original", entries[0]["dest"])] if rel == entries[0]["rel"]
        else []
    )
    viewer = ImageViewer(
        root, entries, 0, steps_lookup=steps_lookup, restore_cb=restore_cb,
        on_restored=restored.append,
    )
    viewer._restore_this_step("Original")
    assert calls == [(entries[0]["rel"], "Original")]
    assert restored == [entries[0]]
    viewer.destroy()


# --- Delete: confirm, remove exactly the displayed file, advance -------


def test_delete_removes_the_file_advances_and_fires_on_deleted(
    root, tmp_path, monkeypatch,
):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    entries = make_entries(tmp_path)
    dest0 = entries[0]["dest"]
    deleted = []
    viewer = ImageViewer(root, entries, 0, on_deleted=deleted.append)

    viewer._delete_current()

    assert not dest0.exists()
    assert len(deleted) == 1
    assert deleted[0]["drop_path"] == entries[0]["drop_path"]
    assert deleted[0]["dest"] is None
    # advanced to the next entry (Hera) rather than staying put
    assert viewer._index == 1
    viewer.destroy()


def test_delete_declined_leaves_the_file_and_never_fires_on_deleted(
    root, tmp_path, monkeypatch,
):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    entries = make_entries(tmp_path)
    dest0 = entries[0]["dest"]
    deleted = []
    viewer = ImageViewer(root, entries, 0, on_deleted=deleted.append)

    viewer._delete_current()

    assert dest0.exists()
    assert deleted == []
    assert viewer._index == 0
    viewer.destroy()


def test_delete_at_the_last_entry_closes_the_viewer(root, tmp_path, monkeypatch):
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    entries = make_entries(tmp_path)
    viewer = ImageViewer(root, entries, 2)  # the LAST entry — nothing to advance to

    viewer._delete_current()

    assert not viewer.winfo_exists()


def test_delete_targets_the_saved_file_even_while_viewing_a_step(
    root, tmp_path, monkeypatch,
):
    """owner G7: Delete always removes the SAVED image file, never a
    Steps preview — even when the main view currently shows a step
    thumbnail instead of the live file."""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    entries = make_entries(tmp_path)
    dest0 = entries[0]["dest"]
    stage_path = tmp_path / "stage_original.png"
    make_png(stage_path)
    steps_lookup = lambda rel: (
        [("Original", stage_path)] if rel == entries[0]["rel"] else []
    )
    viewer = ImageViewer(root, entries, 0, steps_lookup=steps_lookup)
    viewer._view_step_thumb("Original", stage_path)

    viewer._delete_current()

    assert not dest0.exists()
    assert stage_path.exists()  # the step backup itself is untouched
    viewer.destroy()


def test_at_least_one_entry_is_required(root):
    with pytest.raises(ValueError):
        ImageViewer(root, [], 0)
