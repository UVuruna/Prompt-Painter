"""Window registry `uv shot` imports (rules/howto/runner.md).

Every factory below mirrors a builder already proven in
`tests/test_layout_audit_tk.py` (the same fixtures, trimmed to not need
pytest's `tmp_path`/`tk_root` fixtures — `uv shot` runs each window in its
own child process with nothing but this file). PainterGui and every dialog
need a REAL themed root (`ttkbootstrap.Window`), not the bare `tk.Tk()`
`uv shot`'s Tk driver pre-creates, so each factory builds its own — Tk
tolerates more than one interpreter per process and this is a one-shot
child anyway.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TOOLKIT = "tk"

# rules/devices.json — every window must survive both (owner: we build for
# others, pc-low is never the owner's own machine).
MANDATORY_PROFILES = ["laptop-avg", "pc-low"]

#: one tmp dir per child process, reused by every fixture builder below
_TMP = Path(tempfile.mkdtemp(prefix="ppaint_uv_shot_"))


def _make_png(path: Path, size=(64, 64), color=(90, 140, 210, 255)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")


_STYLED = False


def _root():
    """Reuse `uv shot`'s own pre-created default root instead of opening a
    SECOND Tk interpreter (`tb.Window()` creates its own `tk.Tk`): a second
    interpreter is exactly what breaks customtkinter's process-lifetime
    image cache (`gui/icons.py`/CTkImage binds its underlying `PhotoImage`
    to whichever interpreter was default when first rendered) — confirmed
    by hand, `TclError: image "pyimageN" doesn't exist` the instant a
    second root tries to build the same menu. `PainterGui` only needs a
    plain `tk.Tk`; it applies its own theme via `apply_theme`/
    `register_painter_day`. What `ttkbootstrap.Window` adds beyond that
    (DPI awareness + its base ttk style) is replicated here on the SAME
    root, once per process."""
    import tkinter as tk

    global _STYLED
    root = tk._default_root or tk.Tk()  # noqa: SLF001
    root.withdraw()
    if not _STYLED:
        from ttkbootstrap import utility
        from ttkbootstrap.style import Style

        utility.enable_high_dpi_awareness()
        Style("darkly")
        _STYLED = True
    return root


def _built_gui():
    """A real PainterGui, its own root, main view active — the fullest
    realistic state the app ever shows."""
    from gui import app_settings
    from gui.app import PainterGui

    root = _root()
    # never touch the owner's real settings.json from an offscreen shot
    app_settings.save_settings = lambda *_a, **_kw: None
    gui = PainterGui(root)
    root.update_idletasks()
    root.update()
    return gui


# --- the main window --------------------------------------------------


def make_main_window():
    gui = _built_gui()
    gui._set_view("main")
    gui.root.update_idletasks()
    return gui.root


# --- dialogs (same fixtures as tests/test_layout_audit_tk.py) ---------


DOC_SAMPLE_MD = """# Archetype - Glory (a long real-shaped heading)

**Bold heading** -> `assets/emblem/mood/Glory.png`

```
a radiant golden emblem of glory, laurel wreath, sunburst rays,
heraldic shield centered, no reflections, transparent background
```

- a bullet point long enough to exercise wrapping across the window width
- a second bullet with **bold emphasis** inside it, and a third line so
  the Text body is tall enough to matter for _fit_height
"""


def make_doc_window():
    from gui.doc_window import DocWindow

    gui = _built_gui()
    image_path = _TMP / "doc_preview.png"
    _make_png(image_path, size=(420, 420))
    return DocWindow(
        gui.root, "Emblem - Glory (prompt + image)", DOC_SAMPLE_MD,
        hint="Sheet: archetype/mood.md - line 42",
        image_path=image_path,
        on_image_fix=lambda: ("ok", "image re-saved"),
        on_website_fix=lambda: ("gated", "no API key configured"),
    )


def make_image_viewer():
    from gui.image_viewer import ImageViewer

    gui = _built_gui()
    dest0 = _TMP / "Glory_gem.png"
    _make_png(dest0)
    dest2 = _TMP / "Zeus_v2_gem.png"
    _make_png(dest2)
    entries = [
        {
            "title": "Glory", "drop_path": "assets/emblem/mood/Glory.png",
            "rel": "emblem/mood/Glory_gem.png", "dest": dest0,
            "prompt": "a golden glory emblem, radiant with laurel wreath"
                      " and sunburst rays",
            "refused_reason": None,
        },
        {
            "title": "Hera", "drop_path": "assets/emblem/mood/Hera.png",
            "rel": None, "dest": None,
            "prompt": "a hera emblem, regal peacock feathers",
            "refused_reason": "No saved file - refused, skipped, or not"
                              " generated yet.",
        },
        {
            "title": "Zeus", "drop_path": "assets/emblem/mood/Zeus.png",
            "rel": "emblem/mood/Zeus_v2_gem.png", "dest": dest2,
            "prompt": "a zeus emblem, thunderbolt crossed with an eagle",
            "refused_reason": None,
        },
    ]

    def check_lookup(drop_path: str):
        if drop_path != "assets/emblem/mood/Glory.png":
            return None
        return {
            "rel": "emblem/mood/Glory_gem.png",
            "defects": [
                "extra reflections on the shield",
                "background not fully transparent",
            ],
            "raw": "The image shows a golden emblem with visible"
                   " reflections on the shield's surface...",
        }

    def steps_lookup(rel: str):
        if rel != "emblem/mood/Glory_gem.png":
            return []
        stage0 = _TMP / "stage_original.png"
        _make_png(stage0)
        stage1 = _TMP / "stage_bg.png"
        _make_png(stage1)
        return [("Original", stage0), ("BG removed", stage1),
                ("Current", dest0)]

    return ImageViewer(
        gui.root, entries, 0,
        check_lookup=check_lookup, steps_lookup=steps_lookup,
    )


def make_before_after_window():
    from gui.restore_windows import BeforeAfterWindow

    gui = _built_gui()
    pairs = []
    for i, rel in enumerate((
        "emblem/mood/Glory_gem.png", "emblem/mood/Zeus_v2_gem.png",
        "emblem/virtue/Courage_gpt.png",
    )):
        before = _TMP / f"before_{i}.png"
        _make_png(before, color=(200, 200, 200, 255))
        after = _TMP / f"after_{i}.png"
        _make_png(after, color=(40, 180, 90, 255))
        pairs.append({"rel": rel, "before": before, "after": after})
    return BeforeAfterWindow(
        gui.root, "Background removal - before/after", pairs,
        restore_label="RESTORE ALL", restore_cb=lambda: None,
    )


def make_step_restore_window():
    from painter.jobtemp import JobTemp

    from gui.restore_windows import StepRestoreWindow

    gui = _built_gui()
    folder = _TMP / "job_folder"
    rel = "emblem/mood/Glory_gem.png"
    live = folder / rel
    _make_png(live)
    temp = JobTemp("uv_shot_step_restore", folder)
    src = _TMP / "backup_src.png"
    _make_png(src, color=(210, 90, 140, 255))
    for step in ("original", "bg", "crop", "upscale"):
        temp.backup(src, rel, step=step)
    return StepRestoreWindow(gui.root, "Restore pipeline steps - Glory",
                              temp, rel, live)


def make_select_window():
    from painter.config import dest_for
    from painter.sheet_parser import PromptItem, Sheet

    from gui.select_window import SelectWindow

    gui = _built_gui()
    out_base = _TMP / "output"
    gui.out_var.set(str(out_base))

    items_a = (
        PromptItem("Glory", "assets/emblem/mood/Glory.png",
                   "a golden glory emblem", 10),
        PromptItem("Hera", "assets/emblem/mood/Hera.png", "a hera emblem",
                   20, advice="SUPERSEDED - see v2"),
        PromptItem(
            "A very long heading that stresses the wrap of the collection"
            " tree row all the way to the right edge",
            "assets/emblem/mood/LongTitleEntryThatKeepsGoingAndGoingSoThe"
            "WrapMustReflow.png",
            "prompt", 30,
        ),
    )
    sheet_a = Sheet("Mood Archetypes", _TMP / "mood.md", items_a, (), ())

    items_b = (
        PromptItem("Zeus", "assets/emblem/virtue/Zeus.png", "a zeus emblem",
                   5),
        PromptItem("Courage", "assets/emblem/virtue/Courage.png",
                   "a courage emblem", 15),
    )
    sheet_b = Sheet("Virtue Archetypes", _TMP / "virtue.md", items_b, (), ())

    for site in ("chatgpt", "gemini"):
        dest = out_base / dest_for(items_a[0].drop_path, site)
        _make_png(dest)

    return SelectWindow(gui, [sheet_a, sheet_b])


def make_ai_key_wizard():
    from gui.dialogs import AiKeyWizard

    gui = _built_gui()
    # a real AiKeyWizard calls self.wait_window(self) as the last line of
    # __init__, blocking forever in a one-shot child process — neutralise
    # it exactly like the pytest audit does.
    import tkinter as tk
    orig_wait = tk.Misc.wait_window
    tk.Misc.wait_window = lambda self, window=None: None
    try:
        return AiKeyWizard(gui.root, gui)
    finally:
        tk.Misc.wait_window = orig_wait


WINDOWS = {
    "PainterGui": make_main_window,
    "DocWindow": make_doc_window,
    "ImageViewer": make_image_viewer,
    "BeforeAfterWindow": make_before_after_window,
    "StepRestoreWindow": make_step_restore_window,
    "SelectWindow": make_select_window,
    "AiKeyWizard": make_ai_key_wizard,
}
