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
