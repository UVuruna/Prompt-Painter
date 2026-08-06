"""Guard test - THE SPACE & LEGIBILITY LAW, runtime half, Tkinter (rules/GUI.md).

Installed per MIGRATE-LAYOUT.md (owner order 2026-08-06 - the design-review
rollout), at the reference level of Remote User's Qt audit, translated to Tk:

  A. CLIPPED   - a mapped widget was allocated less than its own requested
                 size (winfo_width < winfo_reqwidth) - Tk clips silently
  B. ESCAPES   - a child's on-screen box leaves its parent's box (invisible
                 content no matter how big the screen is)

plus the law's preconditions: the window's minsize is COMPUTED (the project
already derives it from the Main Menu grid - `_apply_min_size`, owner
2026-08-03) and fits THE SCREEN FLOOR 1280x720.

THE REGISTRY (expanded 2026-08-06, MIGRATE-LAYOUT.md step 2 - "every
top-level window is a hole in the guard until it is registered"): every
``tk.Toplevel`` subclass under ``gui/`` is built in its FULLEST realistic
state and audited the same way as the main window.

  1. PainterGui (the root window)     - gui/app.py            - 3 views
  2. DocWindow                        - gui/doc_window.py
  3. ImageViewer                      - gui/image_viewer.py
  4. BeforeAfterWindow                - gui/restore_windows.py
  5. StepRestoreWindow                - gui/restore_windows.py
  6. SelectWindow                     - gui/select_window.py
  7. AiKeyWizard                      - gui/dialogs.py         - FIXED SIZE

7 windows total, 6 registered dialogs + the main window. NOT separately
registered: ``_ModalToolDialog``/``_AiDialog`` (gui/dialogs.py) are abstract
plumbing - ``_ModalToolDialog`` has no concrete instance of its own (its
only concrete subclass chain is ``_AiDialog`` -> ``AiKeyWizard``, which IS
registered) and ``_AiDialog`` has no other live subclass since
``AiSheetDialog`` was retired (faza 4, see gui/dialogs.py's own docstring).

AiKeyWizard is FIXED SIZE (``resizable(False, False)``) and sized to its
own packed content - there is no larger state to reflow into, so it is
audited at its one natural size only (CLIPPED/ESCAPES + the screen-floor
check), never resized to +50%/screen like the others.

Screenshots: every window is built OFF-SCREEN (x=+9000) and fully
transparent - a dialog constructed WHILE off-screen never flashes across
the owner's display (``_OffscreenToplevels`` pins every ``tk.Toplevel``
this way the instant it is born, before its own ``__init__`` can lay out
a single widget at the window manager's default on-screen position; it
also neutralises ``wait_window`` so a modal dialog's own nested event loop
never blocks the audit). Win32 `PrintWindow(PW_RENDERFULLCONTENT)` renders
each window into a bitmap regardless -
`.claude/shots/<Window>.png`, the DESIGN REVIEW input the session must
OPEN and grade >= 8/10 in `.claude/layout-proof.md`
(rules/hooks/layout_guard.py verifies image, opening, and grade).

Honesty note: Tk has no per-widget elide API and no scrollbar-range
introspection as cheap as Qt's - the ELIDED and SCROLL+SLACK checks of the
Qt audits have no direct Tk equivalent here; A+B catch their visible
consequences (squeezed and vanished content).

Also guarded: no audit run may ever write the real ``settings.json`` -
``save_settings`` is monkeypatched to a no-op for the whole run (a dialog
audit sets ``gui.out_var`` to a throwaway tmp folder to exercise the
DONE/traffic-light colouring, and the app's own 1.5s debounced autosave
would otherwise overwrite the owner's real settings file if a run happens
to cross that delay).

Run:  python tests/test_layout_audit_tk.py       (verbose, per view)
      pytest tests/test_layout_audit_tk.py -q    (suite / run_guards)
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
import tkinter as tk
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

FLOOR_WIDTH, FLOOR_HEIGHT = 1280, 720

SHOT_DIR = PROJECT / ".claude" / "shots"

#: px of tolerance before an allocation counts as clipping (Tk borders
#: round by a pixel here and there)
TOLERANCE = 2

VIEWS = ("menu", "main", "running")


# ═══════════════════════════ WINDOW CAPTURE (Win32) ═══════════════════════════


def capture(win: tk.Misc, name: str) -> Path:
    """PrintWindow the off-screen window into a PNG - the picture can never
    be of a different build than the one just measured. Works for any
    top-level Tk widget (the main root, or one of its Toplevel dialogs) -
    each is its own real HWND."""
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = user32.GetAncestor(win.winfo_id(), 2)  # GA_ROOT

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    gdi32.SelectObject(hdc_mem, bitmap)
    ok = user32.PrintWindow(hwnd, hdc_mem, 2)  # PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth, info.biHeight = width, -height  # top-down
    info.biPlanes, info.biBitCount = 1, 32

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(hdc_mem, bitmap, 0, height, buffer,
                    ctypes.byref(info), 0)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    assert ok, (f"PrintWindow refused to render {name} - a design grade "
                "without a picture is worthless, so this is a hard failure")
    image = Image.frombuffer("RGBA", (width, height), buffer.raw,
                             "raw", "BGRA", 0, 1)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"{name}.png"
    image.convert("RGB").save(path, "PNG")
    return path


# ═══════════════════════════ THE CHECKS ═══════════════════════════


def _in_scrolled_canvas(widget) -> bool:
    node = widget
    while node is not None:
        parent = node.master
        if isinstance(parent, tk.Canvas):
            return True
        node = parent
    return False


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def _is_scrollframe_viewport(widget) -> bool:
    """True for a ``gui.scroll.ScrollFrame`` itself, or its own viewport
    ``tk.Canvas`` - both exempt from the CLIPPED (reqwidth/reqheight)
    check, verified by hand (see the audit's own dev history): Tk's
    Canvas ``winfo_reqwidth``/``winfo_reqheight`` is the LARGEST size the
    canvas has ever needed, not a live figure - after ``ScrollFrame.
    _apply_width`` shrinks the embedded body via ``itemconfigure``, the
    canvas's OWN requested size stays stuck at the earlier, larger value
    even though the real on-screen content (``bbox('all')``,
    ``winfo_width``) is correctly sized down. CLIPPED would be a false
    positive here; a genuine "content escapes its container" bug on a
    ScrollFrame/canvas still shows up in ``check_escapes``, which reads
    real on-screen boxes, not this stale request."""
    from gui.scroll import ScrollFrame

    if isinstance(widget, ScrollFrame):
        return True
    return isinstance(widget, tk.Canvas) and isinstance(widget.master, ScrollFrame)


def check_clipped(win) -> list[str]:
    faults = []
    for widget in walk(win):
        if not widget.winfo_ismapped() or _in_scrolled_canvas(widget):
            continue
        if isinstance(widget, tk.Text) or _is_scrollframe_viewport(widget):
            # a bare tk.Text with no explicit width/height requests the
            # Tk DEFAULT character grid (80x24 at the current font) -
            # meaningless as "content that does not fit": every Text in
            # this project wraps ("word") and scrolls, so a smaller
            # allocation is the whole point, never a clip (same honesty
            # note as _in_scrolled_canvas - real content overflow shows
            # up as ESCAPES if it ever leaves the parent's box instead).
            continue
        need_w, need_h = widget.winfo_reqwidth(), widget.winfo_reqheight()
        have_w, have_h = widget.winfo_width(), widget.winfo_height()
        if need_w > have_w + TOLERANCE or need_h > have_h + TOLERANCE:
            faults.append(
                f"CLIPPED {widget.winfo_class()} {widget!r}: has "
                f"{have_w}x{have_h}, requested {need_w}x{need_h}")
    return faults


def check_escapes(win) -> list[str]:
    faults = []
    root_x, root_y = win.winfo_rootx(), win.winfo_rooty()
    root_r = root_x + win.winfo_width()
    root_b = root_y + win.winfo_height()
    for widget in walk(win):
        if not widget.winfo_ismapped() or _in_scrolled_canvas(widget):
            continue
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        r, b = x + widget.winfo_width(), y + widget.winfo_height()
        if (x < root_x - TOLERANCE or y < root_y - TOLERANCE
                or r > root_r + TOLERANCE or b > root_b + TOLERANCE):
            faults.append(
                f"ESCAPES {widget.winfo_class()} {widget!r}: box "
                f"({x},{y})-({r},{b}) leaves the window "
                f"({root_x},{root_y})-({root_r},{root_b})")
    return faults


def audit(win, label: str) -> list[str]:
    return [f"[{label}] {fault}"
            for fault in check_clipped(win) + check_escapes(win)]


def _effective_minimum(win: tk.Misc) -> tuple[int, int]:
    """The declared minsize when there is one, else the widget's own
    requested size (a fixed-size dialog like AiKeyWizard never calls
    ``minsize`` - its "minimum" IS the size its packed content asks for)."""
    width, height = win.wm_minsize()
    if width > 1 and height > 1:
        return width, height
    win.update_idletasks()
    return max(win.winfo_reqwidth(), 1), max(win.winfo_reqheight(), 1)


# ═══════════════════════════ THE AUDIT RUN ═══════════════════════════


#: ScrollFrame (gui/scroll.py) defers its width/scrollregion re-fit past
#: painter.config.RESIZE_SETTLE_MS (150ms) so a window drag never re-fits
#: on every intermediate <Configure> - the audit must wait that long too,
#: or it measures a stale pre-resize layout instead of the real one.
_SETTLE_FLUSH_MS = 220


def settle(win: tk.Misc, width: int, height: int) -> None:
    win.geometry(f"{width}x{height}+9000+40")
    win.update_idletasks()
    win.update()
    # actively pump the event loop until the debounce timer above has
    # had a chance to fire and apply its deferred re-fit
    done = []
    win.after(_SETTLE_FLUSH_MS, lambda: done.append(True))
    while not done:
        win.update()


class _OffscreenToplevels:
    """Context manager: every ``tk.Toplevel`` constructed while active is
    pinned off-screen and fully transparent THE INSTANT it is born - before
    its own subclass ``__init__`` lays out a single widget at whatever
    position the window manager would otherwise pick - so a dialog audit
    never flashes across the owner's screen (the same belt-and-braces
    technique ``run_audit`` already uses for the root window itself, just
    applied at construction time instead of before it, since a Toplevel
    subclass's ``__init__`` is not under this test's control).

    Also neutralises ``wait_window`` (``Misc.wait_window``): a modal
    dialog like ``AiKeyWizard`` calls ``self.wait_window(self)`` as the
    LAST line of its own ``__init__``, starting a nested Tcl event loop
    that would otherwise block this test until the window is destroyed
    from the OUTSIDE - impossible before construction has even returned.
    """

    def __enter__(self):
        self._orig_init = tk.Toplevel.__init__
        self._orig_wait = tk.Misc.wait_window
        orig_init = self._orig_init

        def init(inner_self, master=None, **kw):
            orig_init(inner_self, master, **kw)
            try:
                inner_self.attributes("-alpha", 0.0)
                inner_self.geometry("+9000+40")
            except tk.TclError:
                pass

        tk.Toplevel.__init__ = init
        tk.Misc.wait_window = lambda inner_self, window=None: None
        return self

    def __exit__(self, *exc_info) -> None:
        tk.Toplevel.__init__ = self._orig_init
        tk.Misc.wait_window = self._orig_wait


# --- fake data builders for the six dialog windows -------------------------


def _make_png(path: Path, size: tuple[int, int] = (64, 64),
              color: tuple[int, int, int, int] = (90, 140, 210, 255)) -> None:
    """A tiny REAL, fully decodable PNG (mirrors test_image_viewer.py's own
    ``make_png`` convention - a raw-bytes stub does not survive the real
    ``Image.open().load()`` path every one of these viewers uses)."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")


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


def _doc_window_win(gui, tmp_path: Path):
    from gui.doc_window import DocWindow

    image_path = tmp_path / "doc_preview.png"
    _make_png(image_path, size=(420, 420))
    return DocWindow(
        gui.root, "Emblem - Glory (prompt + image)", DOC_SAMPLE_MD,
        hint="Sheet: archetype/mood.md - line 42",
        image_path=image_path,
        on_image_fix=lambda: ("ok", "image re-saved"),
        on_website_fix=lambda: ("gated", "no API key configured"),
    )


def _image_viewer_win(gui, tmp_path: Path):
    from gui.image_viewer import ImageViewer

    dest0 = tmp_path / "Glory_gem.png"
    _make_png(dest0)
    dest2 = tmp_path / "Zeus_v2_gem.png"
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
        stage0 = tmp_path / "stage_original.png"
        _make_png(stage0)
        stage1 = tmp_path / "stage_bg.png"
        _make_png(stage1)
        return [("Original", stage0), ("BG removed", stage1),
                ("Current", dest0)]

    return ImageViewer(
        gui.root, entries, 0,
        check_lookup=check_lookup, steps_lookup=steps_lookup,
    )


def _before_after_win(gui, tmp_path: Path):
    from gui.restore_windows import BeforeAfterWindow

    pairs = []
    for i, rel in enumerate((
        "emblem/mood/Glory_gem.png", "emblem/mood/Zeus_v2_gem.png",
        "emblem/virtue/Courage_gpt.png",
    )):
        before = tmp_path / f"before_{i}.png"
        _make_png(before, color=(200, 200, 200, 255))
        after = tmp_path / f"after_{i}.png"
        _make_png(after, color=(40, 180, 90, 255))
        pairs.append({"rel": rel, "before": before, "after": after})
    return BeforeAfterWindow(
        gui.root, "Background removal - before/after", pairs,
        restore_label="RESTORE ALL", restore_cb=lambda: None,
    )


def _step_restore_win(gui, tmp_path: Path):
    from painter.jobtemp import JobTemp

    from gui.restore_windows import StepRestoreWindow

    folder = tmp_path / "job_folder"
    rel = "emblem/mood/Glory_gem.png"
    live = folder / rel
    _make_png(live)
    temp = JobTemp("audit_step_restore", folder)
    src = tmp_path / "backup_src.png"
    _make_png(src, color=(210, 90, 140, 255))
    for step in ("original", "bg", "crop", "upscale"):
        temp.backup(src, rel, step=step)
    return StepRestoreWindow(gui.root, "Restore pipeline steps - Glory",
                              temp, rel, live)


def _select_window_win(gui, tmp_path: Path):
    from painter.config import dest_for
    from painter.sheet_parser import PromptItem, Sheet

    from gui.select_window import SelectWindow

    out_base = tmp_path / "output"
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
    sheet_a = Sheet("Mood Archetypes", tmp_path / "mood.md", items_a, (), ())

    items_b = (
        PromptItem("Zeus", "assets/emblem/virtue/Zeus.png", "a zeus emblem",
                   5),
        PromptItem("Courage", "assets/emblem/virtue/Courage.png",
                   "a courage emblem", 15),
    )
    sheet_b = Sheet("Virtue Archetypes", tmp_path / "virtue.md", items_b,
                     (), ())

    # one item DONE on disk for BOTH sites, so the audit exercises the
    # green / traffic-light DONE colouring, not only the empty state
    for site in ("chatgpt", "gemini"):
        dest = out_base / dest_for(items_a[0].drop_path, site)
        _make_png(dest)

    return SelectWindow(gui, [sheet_a, sheet_b])


def _ai_key_wizard_win(gui, tmp_path: Path):
    from gui.dialogs import AiKeyWizard

    return AiKeyWizard(gui.root, gui)


# (name, fixed_size, builder(gui, tmp_path) -> Toplevel)
DIALOG_WINDOWS = (
    ("DocWindow", False, _doc_window_win),
    ("ImageViewer", False, _image_viewer_win),
    ("BeforeAfterWindow", False, _before_after_win),
    ("StepRestoreWindow", False, _step_restore_win),
    ("SelectWindow", False, _select_window_win),
    ("AiKeyWizard", True, _ai_key_wizard_win),
)


def run_dialog_audit(gui, tmp_path: Path, verbose: bool = False) -> list[str]:
    problems: list[str] = []
    with _OffscreenToplevels():
        for name, fixed, builder in DIALOG_WINDOWS:
            win = builder(gui, tmp_path)
            win.update_idletasks()
            win.update()

            min_w, min_h = _effective_minimum(win)
            if min_w <= 0 or min_h <= 0:
                problems.append(f"[{name}] no usable size - the law "
                                "requires one, COMPUTED from real content")
            if min_w > FLOOR_WIDTH or min_h > FLOOR_HEIGHT:
                problems.append(
                    f"[{name}] ABSURD MINIMUM {min_w}x{min_h} - it does "
                    f"not fit the screen floor {FLOOR_WIDTH}x{FLOOR_HEIGHT}"
                )

            sizes = [("minimum", min_w, min_h)]
            if not fixed:
                sizes.append(
                    ("minimum+50%", int(min_w * 1.5), int(min_h * 1.5))
                )
            for size_label, width, height in sizes:
                if width <= 0 or height <= 0:
                    continue
                settle(win, width, height)
                problems += audit(
                    win, f"{name} @ {size_label} {width}x{height}"
                )
                if size_label == "minimum":
                    shot = capture(win, name)
                    if verbose:
                        print(f"SHOT {shot} - MIN {width}x{height} - OPEN "
                              f"it and GRADE it (>= 8/10) in "
                              f".claude/layout-proof.md")

            win.destroy()
    return problems


def run_audit(
    root: tk.Tk, tmp_path: Path, verbose: bool = False,
) -> list[str]:
    """Build + audit the whole app on the GIVEN root - NEVER a fresh,
    separate ``tb.Window()``. ``gui.icons``' icon cache (``_ICONS``) is
    process-lifetime and ties each cached CTkImage's underlying Tk
    PhotoImage to the Tcl INTERPRETER that was live when it was first
    rendered (the exact reason ``tests/conftest.py``'s shared
    ``tk_root`` fixture exists - see its own docstring): a second,
    independently created root is a SEPARATE interpreter, and reusing an
    already-cached image against it raises ``TclError: image "pyimageN"
    doesn't exist`` - confirmed by hand, reproducible with nothing more
    exotic than running any OTHER GUI test ahead of this one in the same
    pytest session. ``main()`` (the standalone CLI entry point, its own
    fresh process) builds and destroys its own root; the pytest test
    passes in the shared ``tk_root`` fixture instead."""
    from gui.app import PainterGui
    from gui import app_settings

    # tests/conftest.py's shared tk_root is WITHDRAWN (never mapped) -
    # PrintWindow needs a real, realized top-level to render, so this
    # audit deiconifies it for its own duration and withdraws it again
    # before returning (every other GUI test in the suite expects it
    # withdrawn, exactly as conftest.py leaves it).
    was_withdrawn = root.state() == "withdrawn"
    if was_withdrawn:
        root.deiconify()
    root.geometry("+9000+40")          # off the 3840px-wide screen
    root.attributes("-alpha", 0.0)     # and fully transparent, belt+braces

    # NEVER let this audit touch the real settings.json (gitignored,
    # holds the owner's real Gemini key / output folder): the dialog
    # audit sets gui.out_var to a throwaway tmp folder, which arms the
    # app's own 1.5s debounced autosave - patched to a no-op for the
    # whole run instead of racing that timer against test duration.
    orig_save = app_settings.save_settings
    app_settings.save_settings = lambda *_a, **_kw: None
    try:
        gui = PainterGui(root)
        root.update_idletasks()
        root.update()

        problems: list[str] = []

        # THE SCREEN FLOOR on the COMPUTED minsize (computed by
        # _apply_min_size from the menu grid - owner 2026-08-03)
        min_w, min_h = root.wm_minsize()
        if min_w <= 0 or min_h <= 0:
            problems.append("[PainterGui] no declared minsize - the law "
                            "requires one, COMPUTED from real content")
        if min_w > FLOOR_WIDTH or min_h > FLOOR_HEIGHT:
            problems.append(
                f"[PainterGui] ABSURD MINIMUM {min_w}x{min_h} - it does not "
                f"fit the screen floor {FLOOR_WIDTH}x{FLOOR_HEIGHT}: the "
                "window demands a screen the user does not have. REFLOW "
                "(ladder step 2) - widening your way out is the bug itself"
            )

        screen_w, screen_h = 2560, 1400   # a fixed large size: deterministic,
        sizes = [                         # and off-screen anyway
            ("minimum", min_w, min_h),
            ("minimum+50%", int(min_w * 1.5), int(min_h * 1.5)),
            ("screen", screen_w, screen_h),
        ]
        for view in VIEWS:
            gui._set_view(view)
            root.update_idletasks()
            for size_label, width, height in sizes:
                if width <= 0 or height <= 0:
                    continue
                settle(root, width, height)
                problems += audit(root, f"PainterGui/{view} @ {size_label} "
                                        f"{width}x{height}")
                if size_label == "minimum":
                    shot = capture(root, f"PainterGui_{view}")
                    if verbose:
                        print(f"SHOT {shot} - MIN {width}x{height} - OPEN "
                              f"it and GRADE it (>= 8/10) in "
                              f".claude/layout-proof.md")

        problems += run_dialog_audit(gui, tmp_path, verbose=verbose)

        if gui._save_job is not None:
            root.after_cancel(gui._save_job)
            gui._save_job = None
    finally:
        app_settings.save_settings = orig_save
        # destroy every widget THIS RUN put on the root, never the root
        # itself - it may be the pytest session's shared tk_root, which
        # every other GUI test in the suite still needs alive after us
        # (mirrors tests/conftest.py's own _reclaim_tk_handles teardown).
        for child in list(root.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        if was_withdrawn:
            root.withdraw()

    return problems


_LADDER = ("\nLadder: (1) the starving element takes the free space, "
           "(2) reflow into more rows, (3) raise the window minimum, "
           "(4) scroll only when the window is genuinely full.")


def test_layout_audit(tk_root, tmp_path) -> None:
    problems = run_audit(tk_root, tmp_path)
    assert not problems, (
        "THE SPACE & LEGIBILITY LAW (rules/GUI.md) - runtime audit "
        "failed:\n  " + "\n  ".join(problems) + _LADDER
    )


def main() -> int:
    import ttkbootstrap as tb

    root = tb.Window(themename="darkly")
    try:
        with tempfile.TemporaryDirectory(prefix="ppaint_layout_audit_") as tmp:
            problems = run_audit(root, Path(tmp), verbose=True)
    finally:
        root.destroy()
    if problems:
        print("LAYOUT AUDIT: FAIL", file=sys.stderr)
        for problem in problems:
            print("  " + problem, file=sys.stderr)
        return 1
    print(f"LAYOUT AUDIT: PASS (PainterGui: 3 views x minimum, +50%, "
          f"screen; {len(DIALOG_WINDOWS)} dialogs: minimum"
          f"{'+50%' if any(not f for _, f, _ in DIALOG_WINDOWS) else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
