"""Zubi v2 — the Tk TEMPLATE (first Tk rollout: PromptPainter,
2026-08-11, owner's order after the BobaFett_v2 refused-view shots).

Algorithmic checks measured by plain code — no AI in the loop
(rules/GUI.md -> Zubi v2). This module is the Tk counterpart of
`rules/templates/layout_checks_qt.py`; the root repo carries a copy as
`rules/templates/layout_checks_tk.py` for the next Tk project.

Implemented here (the subset measurable in Tk today, each mapped to
its rule):

- ALG-5 UNIFORM SIBLINGS — same-kind buttons sharing one visual row
  share height (tolerance ±2 px).
- ALG-6 RADIUS BY ASPECT RATIO — every CTk widget with a corner_radius
  keeps it inside the percent tiers (AR >= 2: r <= 50% of height;
  1.4 <= AR < 2: <= 30% of height; squarish: <= 30% of the shorter
  side). True-circle content is exempt by the same rule.
- ALG-7 EMPTY BAND (the owner's BUG A, measured) — a widget that
  SCROLLS (a Text with more display lines than visible rows, or a
  scroll canvas whose scrollregion exceeds its viewport) while the
  same window still holds >= EMPTY_BAND_PX of free vertical space is a
  violation: the free space had to be taken first (the ladder).

Still on the GRADER's checklist, not measured here (documented gap,
same honesty as the Qt template's own): ALG-2 contrast sampling,
ALG-3 hover geometry, ALG-8 live profile, ALG-9 section taxonomy.
"""

from __future__ import annotations

import tkinter as tk

TOLERANCE = 2
#: free vertical space that counts as a DEAD BAND when something scrolls
EMPTY_BAND_PX = 150


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _mapped(widget) -> bool:
    try:
        return bool(widget.winfo_ismapped())
    except Exception:
        return False


# ═══════════════ ALG-5 — UNIFORM SIBLINGS ═══════════════


def check_uniform_siblings(win, label: str) -> list[str]:
    """Same-kind buttons sharing one visual ROW (vertical overlap of
    their boxes) share HEIGHT within ±2 px — a control's size never
    depends on the length of its own text."""
    faults: list[str] = []
    for parent in _walk(win):
        buttons = [
            c for c in parent.winfo_children()
            if _mapped(c) and c.winfo_class() in (
                "TButton", "Button", "CTkButton",
            )
        ]
        if len(buttons) < 2:
            continue
        # group into visual rows by vertical-center proximity
        rows: list[list] = []
        for b in sorted(buttons, key=lambda w: w.winfo_rooty()):
            cy = b.winfo_rooty() + b.winfo_height() / 2
            for row in rows:
                r0 = row[0]
                rcy = r0.winfo_rooty() + r0.winfo_height() / 2
                if abs(cy - rcy) <= r0.winfo_height() / 2:
                    row.append(b)
                    break
            else:
                rows.append([b])
        for row in rows:
            if len(row) < 2:
                continue
            heights = [b.winfo_height() for b in row]
            if max(heights) - min(heights) > TOLERANCE:
                faults.append(
                    f"[{label}] ALG-5 UNIFORM SIBLINGS: buttons in one"
                    f" row of {parent.winfo_class()} differ in height"
                    f" {sorted(set(heights))} (tolerance ±{TOLERANCE})"
                )
    return faults


# ═══════════════ ALG-6 — RADIUS BY ASPECT RATIO ═══════════════


def check_radius(win, label: str) -> list[str]:
    faults: list[str] = []
    for widget in _walk(win):
        if not _mapped(widget):
            continue
        try:
            r = widget.cget("corner_radius")
        except Exception:
            continue
        if not isinstance(r, (int, float)) or r <= 0:
            continue
        w, h = widget.winfo_width(), widget.winfo_height()
        if w <= 1 or h <= 1:
            continue
        # CTk clamps the DRAWN radius to half the shorter side — a
        # declared 1000 on a 30px-tall pill renders as 15. Judge what
        # renders, not the declared number (a circle on a squarish
        # element still fails: half the side = 50% > the 30% tier).
        r = min(float(r), w / 2, h / 2)
        ar = w / h
        if ar >= 2:
            cap, base = 0.50, h
        elif ar >= 1.4:
            cap, base = 0.30, h
        else:
            cap, base = 0.30, min(w, h)
        if r > cap * base + TOLERANCE:
            faults.append(
                f"[{label}] ALG-6 RADIUS: {widget.winfo_class()}"
                f" {w}x{h} (AR {ar:.2f}) carries corner_radius {r}px"
                f" > {cap:.0%} of {base}px"
            )
    return faults


# ═══════════════ ALG-7 — EMPTY BAND (BUG A, measured) ═══════════════


def _scrolling_widgets(win) -> list[str]:
    """Descendants whose CONTENT exceeds their viewport (they scroll)."""
    scrolling: list[str] = []
    for widget in _walk(win):
        if not _mapped(widget):
            continue
        if isinstance(widget, tk.Text):
            try:
                lines = widget.count("1.0", "end", "displaylines")[0]
                visible = int(widget.cget("height"))
            except Exception:
                continue
            if lines > visible + 1:
                scrolling.append(f"Text({lines} lines in {visible} rows)")
        elif isinstance(widget, tk.Canvas):
            region = widget.cget("scrollregion")
            if not region:
                continue
            try:
                _l, _t, _r, bottom = (int(float(v)) for v in region.split())
            except Exception:
                continue
            if bottom > widget.winfo_height() + TOLERANCE * 4:
                scrolling.append(
                    f"Canvas(content {bottom}px in"
                    f" {widget.winfo_height()}px viewport)"
                )
    return scrolling


def check_empty_band(win, label: str) -> list[str]:
    """The owner's BUG A: something scrolls while the window still
    holds a dead band of free vertical space >= EMPTY_BAND_PX. The
    free space had to be taken FIRST (ladder step 1); the scrollbar is
    legal only in a genuinely full window."""
    scrolling = _scrolling_widgets(win)
    if not scrolling:
        return []
    # free space = window height minus the LOWEST mapped widget bottom
    win_bottom = win.winfo_rooty() + win.winfo_height()
    content_bottom = max(
        (
            w.winfo_rooty() + w.winfo_height()
            for w in _walk(win)
            if _mapped(w) and not isinstance(w, tk.Toplevel)
        ),
        default=win_bottom,
    )
    slack = win_bottom - content_bottom
    if slack >= EMPTY_BAND_PX:
        return [
            f"[{label}] ALG-7 EMPTY BAND: {slack}px of free vertical"
            f" space below the content while {', '.join(scrolling)}"
            " scroll(s) — take the free space before any scrollbar"
        ]
    return []


def run_zubi(win, label: str) -> list[str]:
    """All implemented Zubi v2 Tk checks over one laid-out window."""
    return (
        check_uniform_siblings(win, label)
        + check_radius(win, label)
        + check_empty_band(win, label)
    )
