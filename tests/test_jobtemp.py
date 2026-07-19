"""JobTemp + measure — the four tools' backup/restore + before→after math.

Backups round-trip byte-identical, a no-op backup can be dropped,
restore_all reverts the whole job, clear() wipes the slot, and measure()
reports the right % for all four kinds — including the larger-axis
aspect stretch where a naive "smaller side only" reading would report 0.
Everything runs on synthetic PNGs; the temp root is swept after each
test.
"""

import numpy as np
import pytest
from PIL import Image

from painter.jobtemp import JobTemp, TEMP_ROOT, clear_all, measure


@pytest.fixture(autouse=True)
def _sweep_temp():
    yield
    clear_all()


def _make_png(path, w, h, mode="RGBA", fill=(180, 60, 60, 255)):
    if mode == "RGBA":
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[h // 4:3 * h // 4, w // 4:3 * w // 4] = fill
        Image.fromarray(arr, "RGBA").save(path, "PNG")
    else:
        arr = np.full((h, w, 3), 255, dtype=np.uint8)
        arr[h // 4:3 * h // 4, w // 4:3 * w // 4] = fill[:3]
        Image.fromarray(arr, "RGB").save(path, "PNG")


# --- JobTemp ----------------------------------------------------------


def test_backup_restore_one_round_trips_bytes(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "a.png"
    _make_png(img, 40, 40)
    original = img.read_bytes()

    jt = JobTemp("bg", folder)
    jt.backup(img, "a.png")
    assert jt.has_backup("a.png")
    # the tool "changes" the file in place
    img.write_bytes(b"totally different bytes")
    assert img.read_bytes() != original

    assert jt.restore_one("a.png") is True
    assert img.read_bytes() == original  # byte-identical restore


def test_before_path_points_at_the_backup(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "b.png"
    _make_png(img, 20, 20)
    jt = JobTemp("crop", folder)
    bak = jt.backup(img, "b.png")
    assert jt.before_path("b.png") == bak
    assert jt.before_path("missing.png") is None


def test_drop_removes_a_no_op_backup(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "c.png"
    _make_png(img, 20, 20)
    jt = JobTemp("crop", folder)
    jt.backup(img, "c.png")
    jt.drop("c.png")
    assert not jt.has_backup("c.png")
    assert jt.restore_one("c.png") is False  # nothing to restore


def test_restore_all_reverts_every_backed_up_file(tmp_path):
    folder = tmp_path / "imgs"
    (folder / "sub").mkdir(parents=True)
    files = {
        "one.png": folder / "one.png",
        "sub/two.png": folder / "sub" / "two.png",
        "three.png": folder / "three.png",
    }
    originals = {}
    jt = JobTemp("upscale", folder)
    for rel, path in files.items():
        _make_png(path, 30, 30)
        originals[rel] = path.read_bytes()
        jt.backup(path, rel)
        path.write_bytes(b"stomped " + rel.encode())

    assert jt.restore_all() == 3
    for rel, path in files.items():
        assert path.read_bytes() == originals[rel]


def test_clear_removes_the_slot_dir(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "d.png"
    _make_png(img, 20, 20)
    jt = JobTemp("aspect", folder)
    jt.backup(img, "d.png")
    assert jt.root.exists()
    jt.clear()
    assert not jt.root.exists()


def test_clear_all_wipes_the_whole_root(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "e.png"
    _make_png(img, 20, 20)
    JobTemp("bg", folder).backup(img, "e.png")
    JobTemp("crop", folder).backup(img, "e.png")
    assert TEMP_ROOT.exists()
    clear_all()
    assert not TEMP_ROOT.exists()


def test_new_jobtemp_wipes_a_stale_slot(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "f.png"
    _make_png(img, 20, 20)
    JobTemp("bg", folder).backup(img, "f.png")
    # a fresh JobTemp for the SAME slot must start empty
    jt2 = JobTemp("bg", folder)
    assert not jt2.has_backup("f.png")


# --- measure ----------------------------------------------------------


def test_measure_bg_counts_removed_pixels(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    # before: fully opaque white plate (RGB)
    _make_png(before, 100, 100, mode="RGB")
    # after: same size, a 20x20 corner cleared to transparent
    arr = np.full((100, 100, 4), 255, dtype=np.uint8)
    arr[:20, :20, 3] = 0
    Image.fromarray(arr, "RGBA").save(after, "PNG")

    m = measure("bg", before, after)
    assert m["before"] == "100x100"
    assert m["after"] == "100x100"
    assert m["label"] == "removed"
    assert abs(m["pct"] - 4.0) < 0.01  # 400 / 10000 = 4%


def test_measure_crop_reports_area_reduction(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 100, 100)
    _make_png(after, 60, 60)
    m = measure("crop", before, after)
    assert m["label"] == "reduction"
    # (100^2 - 60^2) / 100^2 = 0.64
    assert abs(m["pct"] - 64.0) < 0.01


def test_measure_upscale_reports_area_increase(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 100, 100)
    _make_png(after, 200, 200)
    m = measure("upscale", before, after)
    assert m["label"] == "increase"
    # (200^2 - 100^2) / 100^2 = 3.0 -> 300%
    assert abs(m["pct"] - 300.0) < 0.01


def test_measure_aspect_reports_changed_axis_growth(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 1024, 1024)
    _make_png(after, 1820, 1024)  # width stretched, height kept
    m = measure("aspect", before, after)
    assert m["label"] == "deformation"
    assert abs(m["pct"] - 77.73) < 0.1  # (1820-1024)/1024


def test_measure_aspect_larger_axis_stretch_is_not_zero(tmp_path):
    """The case a literal 'smaller side only' reading gets wrong: the
    LARGER axis is stretched, the smaller is untouched — deformation is
    the larger axis's growth, never 0."""
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 1000, 900)
    _make_png(after, 1600, 900)  # width (larger axis) stretched
    m = measure("aspect", before, after)
    assert abs(m["pct"] - 60.0) < 0.01  # (1600-1000)/1000, NOT 0
