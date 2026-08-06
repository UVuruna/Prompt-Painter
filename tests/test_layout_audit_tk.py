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

The whole window is audited in all three of its views (menu / main /
running) at the declared minimum, at minimum+50% and at the full screen
size. Content inside a scrolling Canvas is exempt from A/B - it is SUPPOSED
to exceed the viewport and stays reachable.

Screenshots: the window is built OFF-SCREEN (x=+9000) and fully
transparent, so nothing flashes on the owner's display; Win32
`PrintWindow(PW_RENDERFULLCONTENT)` renders it into a bitmap anyway -
`.claude/shots/<Window>_<view>.png`, the DESIGN REVIEW input the session
must OPEN and grade >= 8/10 in `.claude/layout-proof.md`
(rules/hooks/layout_guard.py verifies image, opening, and grade).

Honesty note: Tk has no per-widget elide API and no scrollbar-range
introspection as cheap as Qt's - the ELIDED and SCROLL+SLACK checks of the
Qt audits have no direct Tk equivalent here; A+B catch their visible
consequences (squeezed and vanished content).

Run:  python tests/test_layout_audit_tk.py       (verbose, per view)
      pytest tests/test_layout_audit_tk.py -q    (suite / run_guards)
"""

from __future__ import annotations

import ctypes
import sys
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


def capture(root: tk.Tk, name: str) -> Path:
    """PrintWindow the off-screen window into a PNG - the picture can never
    be of a different build than the one just measured."""
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT

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


def check_clipped(root) -> list[str]:
    faults = []
    for widget in walk(root):
        if not widget.winfo_ismapped() or _in_scrolled_canvas(widget):
            continue
        need_w, need_h = widget.winfo_reqwidth(), widget.winfo_reqheight()
        have_w, have_h = widget.winfo_width(), widget.winfo_height()
        if need_w > have_w + TOLERANCE or need_h > have_h + TOLERANCE:
            faults.append(
                f"CLIPPED {widget.winfo_class()} {widget!r}: has "
                f"{have_w}x{have_h}, requested {need_w}x{need_h}")
    return faults


def check_escapes(root) -> list[str]:
    faults = []
    root_x, root_y = root.winfo_rootx(), root.winfo_rooty()
    root_r = root_x + root.winfo_width()
    root_b = root_y + root.winfo_height()
    for widget in walk(root):
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


def audit(root, label: str) -> list[str]:
    return [f"[{label}] {fault}"
            for fault in check_clipped(root) + check_escapes(root)]


# ═══════════════════════════ THE AUDIT RUN ═══════════════════════════


def settle(root, width: int, height: int) -> None:
    root.geometry(f"{width}x{height}+9000+40")
    root.update_idletasks()
    root.update()


def run_audit(verbose: bool = False) -> list[str]:
    import ttkbootstrap as tb

    from gui.app import PainterGui

    root = tb.Window(themename="darkly")
    root.geometry("+9000+40")          # off the 3840px-wide screen
    root.attributes("-alpha", 0.0)     # and fully transparent, belt+braces
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
            f"[PainterGui] ABSURD MINIMUM {min_w}x{min_h} - it does not fit "
            f"the screen floor {FLOOR_WIDTH}x{FLOOR_HEIGHT}: the window "
            "demands a screen the user does not have. REFLOW (ladder "
            "step 2) - widening your way out is the bug itself")

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
                    print(f"SHOT {shot} - MIN {width}x{height} - OPEN it "
                          f"and GRADE it (>= 8/10) in "
                          f".claude/layout-proof.md")

    root.destroy()
    return problems


_LADDER = ("\nLadder: (1) the starving element takes the free space, "
           "(2) reflow into more rows, (3) raise the window minimum, "
           "(4) scroll only when the window is genuinely full.")


def test_layout_audit() -> None:
    problems = run_audit()
    assert not problems, (
        "THE SPACE & LEGIBILITY LAW (rules/GUI.md) - runtime audit "
        "failed:\n  " + "\n  ".join(problems) + _LADDER
    )


def main() -> int:
    problems = run_audit(verbose=True)
    if problems:
        print("PainterGui: FAIL", file=sys.stderr)
        for problem in problems:
            print("  " + problem, file=sys.stderr)
        return 1
    print("PainterGui: PASS (3 views x minimum, +50%, screen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
