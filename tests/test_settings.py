"""Settings persistence (owner's #9) — missing, roundtrip, corrupt."""

import painter.settings as settings_mod
from painter.settings import load_settings, save_settings


def point_at(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
    return path


def test_missing_file_is_empty(monkeypatch, tmp_path):
    point_at(monkeypatch, tmp_path)
    assert load_settings() == {}


def test_roundtrip(monkeypatch, tmp_path):
    path = point_at(monkeypatch, tmp_path)
    data = {"site": "gemini", "pause": [30, 75], "upscale": True}
    save_settings(data)
    assert path.exists()
    assert load_settings() == data
    assert not path.with_name(path.name + ".tmp").exists()  # atomic


def test_roundtrip_upscale_and_dialog_schema(monkeypatch, tmp_path):
    """The owner 2026-07-19 keys survive the JSON round-trip verbatim:
    the per-agent upscale-gate fine-tune, the standalone Upscale dialog's
    last-used params, the last aspect W:H, and the Settings-collapse
    state (nested dicts / lists / bools intact)."""
    path = point_at(monkeypatch, tmp_path)
    data = {
        "settings_collapsed": False,
        "upscale_tool": {
            "min_width": 1000, "min_height": 600,
            "aspect_min": 0.8, "aspect_max": 1.25,
        },
        "aspect_ratio": [4, 3],
        "agents": {
            "gemini": {
                "up_minw": "900", "up_minh": "900",
                "up_aspmin": "0.85", "up_aspmax": "1.15",
            },
        },
    }
    save_settings(data)
    assert load_settings() == data


def test_corrupt_file_is_loud_but_returns_empty(
    monkeypatch, tmp_path, capsys
):
    path = point_at(monkeypatch, tmp_path)
    path.write_text("{not json at all", encoding="utf-8")
    assert load_settings() == {}
    assert "SETTINGS" in capsys.readouterr().err


def test_non_dict_json_is_loud_but_returns_empty(
    monkeypatch, tmp_path, capsys
):
    path = point_at(monkeypatch, tmp_path)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_settings() == {}
    assert "SETTINGS" in capsys.readouterr().err
