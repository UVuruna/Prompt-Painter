"""``SheetGenPanel`` (faza 4, owner UV tačka 4 — the New Collection
(AI) wizard as a real setup panel) + ``ModelPickerRow`` (the shared
per-purpose model picker the checker/sheet-generator host). Workers
run synchronously via the same _ImmediateThread convention
test_gui_api_image.py established; the ai module is monkeypatched —
no real API calls anywhere here."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import gui
from painter import ai as ai_module


@pytest.fixture
def root(tk_root):
    return tk_root


class _ImmediateThread:
    """threading.Thread stand-in: run() executes inline on start()."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self) -> None:
        self._target()


def _host(root, key_ok: bool = True):
    """A duck-typed PainterGui host: only what SheetGenPanel reads."""
    logged: list[str] = []
    queued: list[Path] = []
    host = SimpleNamespace(
        _ensure_ai_key=lambda: key_ok,
        _q=SimpleNamespace(put=logged.append),
        add_generated_sheet=queued.append,
        _scroll=SimpleNamespace(refresh=lambda: None),
        logged=logged, queued=queued,
    )
    return host


GOOD_MD = (
    "# Test Theme\n\n"
    "**Hero** → `assets/x/Hero.png`\n\n"
    "```\nA hero prompt. ASPECT RATIO 1:1.\n```\n"
)
BAD_MD = (
    "# Test Theme\n\n"
    "**Hero** → `assets/x/Hero.png`\n\n"
    "no fence follows — the entry has no prompt block\n"
)


def _drain(panel):
    """Apply every queued worker message synchronously."""
    while True:
        try:
            msg = panel._q.get_nowait()
        except Exception:
            return
        panel._on_message(msg)


def test_ask_shows_the_models_questions(root, monkeypatch):
    monkeypatch.setattr(gui.sheetgen_panel.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(ai_module, "contract_text", lambda: "CONTRACT")
    monkeypatch.setattr(
        ai_module, "ask_questions",
        lambda request, contract: ["How many images?", "What style?"],
    )
    host = _host(root)
    panel = gui.SheetGenPanel(root, host)
    panel._request_txt.insert("1.0", "Napravi mi 12 slika Astrologije")

    panel._ask()
    _drain(panel)

    assert panel._questions == ["How many images?", "What style?"]
    assert len(panel._answer_vars) == 2
    assert panel._questions_box.winfo_manager() == "pack"
    assert panel._contract == "CONTRACT"


def test_ask_without_a_key_never_calls_the_model(root, monkeypatch):
    called = []
    monkeypatch.setattr(
        ai_module, "ask_questions",
        lambda *a, **k: called.append(1) or [],
    )
    host = _host(root, key_ok=False)
    panel = gui.SheetGenPanel(root, host)
    panel._request_txt.insert("1.0", "anything")
    panel._ask()
    assert called == []
    assert not panel._busy


def test_generate_shows_the_editable_draft(root, monkeypatch):
    monkeypatch.setattr(gui.sheetgen_panel.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        ai_module, "generate_sheet",
        lambda *a, **k: (GOOD_MD, [], "Test Theme"),
    )
    host = _host(root)
    panel = gui.SheetGenPanel(root, host)
    panel._request, panel._contract = "req", "CONTRACT"

    panel._generate()
    _drain(panel)

    assert panel._draft_box.winfo_manager() == "pack"
    assert "Hero" in panel._draft_txt.get("1.0", "end")
    assert "contract-clean" in panel._status_var.get()


def test_save_validates_the_edited_draft_and_blocks_problems(
    root, monkeypatch, tmp_path,
):
    host = _host(root)
    panel = gui.SheetGenPanel(root, host)
    panel.save_dir_var.set(str(tmp_path))
    panel._draft_txt.insert("1.0", BAD_MD)

    panel._save(queue_it=True)

    assert "NOT SAVED" in panel._status_var.get()
    assert host.queued == []
    assert list(tmp_path.glob("*.md")) == []


def test_save_writes_the_md_and_optionally_queues(root, tmp_path):
    host = _host(root)
    panel = gui.SheetGenPanel(root, host)
    panel.save_dir_var.set(str(tmp_path))
    panel._draft_txt.insert("1.0", GOOD_MD)

    panel._save(queue_it=False)
    saved = list(tmp_path.glob("*.md"))
    assert len(saved) == 1
    assert host.queued == []  # Save alone never queues

    panel._save(queue_it=True)
    assert len(host.queued) == 1  # Save + Add to queue does


def test_settings_round_trip(root):
    host = _host(root)
    panel = gui.SheetGenPanel(root, host)
    panel.save_dir_var.set("U:/somewhere")
    stored = panel.get_settings()
    fresh = gui.SheetGenPanel(root, _host(root))
    fresh.apply_settings(stored, conditions=None)
    assert fresh.save_dir_var.get() == "U:/somewhere"


# --- ModelPickerRow ---------------------------------------------------

FAKE_MODELS = [
    {"name": "gemini-flash-latest", "methods": ("generateContent",),
     "display": "Flash"},
    {"name": "gemini-3.1-pro", "methods": ("generateContent",),
     "display": "Pro"},
    {"name": "text-embedding-004", "methods": ("embedContent",),
     "display": "Embedding"},
]


def test_model_picker_populates_capable_and_hints(root, monkeypatch):
    from painter import settings as settings_module

    monkeypatch.setattr(gui.model_picker.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(ai_module, "list_models", lambda **k: FAKE_MODELS)
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    row = gui.ModelPickerRow(root, "text", "Text")

    row._refresh()
    row._apply_result(row._q.get_nowait())

    values = row._combo.cget("values")
    assert "text-embedding-004" not in values      # not text-capable
    assert row.model_var.get() == "gemini-3.1-pro"  # the ranked pick
    assert row._hint_var.get()                      # a curated hint shows


def test_model_picker_pick_persists_the_override(root, monkeypatch):
    from painter import settings as settings_module
    from painter.config import MODELS_SETTING

    saved: dict = {}
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    monkeypatch.setattr(
        settings_module, "save_settings", lambda d: saved.update(d),
    )
    row = gui.ModelPickerRow(root, "vision", "Vision")
    row._on_pick("gemini-3.1-pro")
    assert saved[MODELS_SETTING] == {"vision": "gemini-3.1-pro"}


def test_checker_panel_hosts_the_vision_picker(root):
    """Faza 4 (owner UV tačka 5): the Vision pick lives on the AI
    Check panel — the surface that USES it."""
    panel = gui.ImageCheckerSettingsPanel(
        root, on_start=lambda: None, on_pause=lambda *_a: None,
        on_stop=lambda *_a: None,
    )
    assert isinstance(panel.model_picker, gui.ModelPickerRow)
    assert panel.model_picker._purpose == "vision"