"""Dashboard support helpers pulled out of ``gui/__init__.py`` (god-file
refactor, Rule #20): the badge-dot PhotoImage cache, the tool-panel
timing summary line, the AI-check report/tag helpers shared by
``AiCheckPanel`` and ``DashPanel``, the shared ``Treeview`` builder
behind every job-panel table, and the before/after viewer's
transparency-checkerboard compositing helpers.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from painter.config import (
    BADGE_DOT_GAP_PX,
    BADGE_DOT_PX,
    BADGE_DOT_SS,
    BADGES,
    CHECKER_DARK,
    CHECKER_LIGHT,
    CHECKER_TILE_PX,
    fmt_op_duration,
)
from .theme import TOOL_CHANGED_TAG, TOOL_SKIP_TAG, skin_tree

# --- Status badge dots (owner 2026-07-20) ----------------------------
# Small coloured dots beside an image row's name in the gen panels'
# Collections tree — one per post-save step that actually CHANGED the
# image (config.badge_keys_for over the runner's action string), plus
# the safer-retry mark. PIL-DRAWN: Tk 8.6 on Windows renders colour
# emoji as identical monochrome circles (probed live 2026-07-20), so
# glyph badges cannot be told apart — the dots are rasterized
# supersampled + LANCZOS like all GUI art and attached as the row's
# Treeview image (the only per-row colour a ttk.Treeview offers; it
# sits LEFT of the name). Colours/labels are config data (BADGES); one
# PhotoImage per key-combination, cached for the process lifetime so
# tk can never GC a row's image.
_BADGE_DOTS: dict[tuple[str, ...], ImageTk.PhotoImage] = {}


def badge_dots(keys: tuple[str, ...]) -> ImageTk.PhotoImage | None:
    """The cached dot-strip PhotoImage for one badge-key combination —
    None when the image earned no badges (the row then carries no
    image and keeps the plain indent)."""
    if not keys:
        return None
    photo = _BADGE_DOTS.get(keys)
    if photo is None:
        ss = BADGE_DOT_SS
        d, gap = BADGE_DOT_PX * ss, BADGE_DOT_GAP_PX * ss
        strip = Image.new(
            "RGBA", (len(keys) * d + (len(keys) - 1) * gap, d), (0, 0, 0, 0)
        )
        draw = ImageDraw.Draw(strip)
        for i, key in enumerate(keys):
            x = i * (d + gap)
            draw.ellipse([x, 0, x + d - 1, d - 1], fill=BADGES[key][0])
        photo = ImageTk.PhotoImage(
            strip.resize(
                (strip.width // ss, strip.height // ss), Image.LANCZOS
            )
        )
        _BADGE_DOTS[keys] = photo
    return photo


def fmt_time_summary(times: list[float]) -> str:
    """The '⏱ Xs total · Ys/img' stat line shared by the in-place tool
    panels and the AI-check panel (Rule #5): the total op time over the
    processed images and the per-image average; '⏱ —' before anything
    has been timed."""
    if not times:
        return "⏱ —"
    total = sum(times)
    return (
        f"⏱ {fmt_op_duration(total)} total"
        f"   ·   {fmt_op_duration(total / len(times))}/img"
    )


def ai_check_doc_md(
    rel: str, defects: list[str] | None, raw: str | None
) -> str:
    """The DocWindow markdown for one AI-checked image (owner
    2026-07-21): the name + path, the parsed defects (when any) AND the
    VERBATIM raw model response under 'Full AI response:' — so the owner
    sees EXACTLY what the vision model said, not only the parsed
    bullets. The raw goes in a code fence (rendered monospace,
    verbatim). SHARED (GUI rework Phase 16, Rule #5): both
    ``AiCheckPanel``'s own double-click viewer and ``DashPanel``'s
    per-row 'Check…' report viewer call this SAME function, so the two
    surfaces can never render a checked image's report differently."""
    parts = [f"# {PurePosixPath(rel).name}\n", f"`{rel}`\n"]
    if defects:
        bullets = "\n".join(f"- {d}" for d in defects)
        parts.append(f"**AI-flagged defects:**\n\n{bullets}\n")
    if raw is not None:
        parts.append(f"**Full AI response:**\n\n```\n{raw.strip()}\n```\n")
    return "\n".join(parts)


def ai_check_image_file(rel: str, out_base: Path) -> Path:
    """The image file behind one flag key — the SAME round-trip the
    checker's ``flag_key`` reverses (``ai.flag_file``), so a report
    viewer can never open a different image than the one that was
    actually checked. SHARED (GUI rework Phase 16, promoted from
    ``AiCheckPanel``'s own private ``_file_for``, Rule #5): both
    ``AiCheckPanel`` and ``DashPanel``'s per-row 'Check…' viewer
    resolve through this ONE function."""
    from painter import ai

    return ai.flag_file(rel, out_base)


def ai_check_tag(kind: str) -> str:
    """The Treeview status TAG for one checked image's 'kind'
    ('flagged'/'ok'/'error') — SHARED (GUI rework Phase 16, Rule #5) by
    ``AiCheckPanel``'s own defect rows and ``DashPanel``'s per-image
    check-status column, so a flagged image pops the same striking
    colour in both views. Only 'flagged' needs attention (the bright
    CHANGED tag); 'ok' and 'error' both stay muted (SKIP) — the actual
    wording ("OK" vs "error"/"!") already tells them apart, no separate
    colour is needed for that distinction."""
    return TOOL_CHANGED_TAG if kind == "flagged" else TOOL_SKIP_TAG


def build_job_tree(panel, col_specs, height: int = 8) -> ttk.Treeview:
    """The rowed table a job panel shows (ToolPanel + AiCheckPanel —
    Rule #5, one home for the identical plumbing): a Treeview with the
    given ``(id, heading, width, anchor)`` value columns, round v/h
    scrollbars in a grid-managed wrap, and the theme-following row tags
    (skin_tree). The caller keeps the column ids and binds its own
    double-click."""
    wrap = ttk.Frame(panel)
    wrap.pack(fill="both", expand=True, pady=(2, 0))
    tree = ttk.Treeview(
        wrap, columns=tuple(c[0] for c in col_specs), height=height
    )
    tree.heading("#0", text="Name")
    tree.column("#0", width=200, minwidth=120, stretch=False)
    for cid, txt, w, anc in col_specs:
        tree.heading(cid, text=txt)
        tree.column(cid, width=w, minwidth=w, anchor=anc, stretch=False)
    vsb = ttk.Scrollbar(
        wrap, orient="vertical", command=tree.yview, bootstyle="round",
    )
    hsb = ttk.Scrollbar(
        wrap, orient="horizontal", command=tree.xview, bootstyle="round",
    )
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    wrap.rowconfigure(0, weight=1)
    wrap.columnconfigure(0, weight=1)
    # the CHANGED/SKIPPED row tags follow the active theme's status
    # colours and re-tint on a flip (the plain-tk skin registry)
    skin_tree(tree)
    return tree


def _checkerboard(w: int, h: int) -> Image.Image:
    """A neutral light/dark checkerboard the size WxH — the transparency
    backdrop so a removed (transparent) background reads as removed, not
    as the panel colour."""
    tile = CHECKER_TILE_PX
    board = Image.new("RGB", (w, h), CHECKER_LIGHT)
    dark = Image.new("RGB", (tile, tile), CHECKER_DARK)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2:
                board.paste(dark, (x, y))
    return board


def _has_alpha(img: Image.Image) -> bool:
    """Whether an image carries transparency (RGBA/LA, or a palette with
    a transparency entry)."""
    return img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _scaled_photo(
    path: Path, avail_px: int, on_checker: bool = False
) -> ImageTk.PhotoImage:
    """One image loaded and scaled to fit ``avail_px`` wide (never
    upscaled), as a live PhotoImage the caller must keep a ref to.
    Shared by DocWindow's prompt image and the BeforeAfterWindow viewer
    (Rule #5). With ``on_checker`` a transparent image is composited over
    a checkerboard so the transparency is VISIBLE (the tool viewer's
    AFTER — a cleared background — otherwise shows the panel colour and
    looks unchanged). Raises OSError on an unreadable file (the caller
    reports it)."""
    img = Image.open(path)
    img.load()
    if img.width > avail_px:
        scale = avail_px / img.width
        img = img.resize(
            (avail_px, max(round(img.height * scale), 1)), Image.LANCZOS
        )
    if on_checker and _has_alpha(img):
        rgba = img.convert("RGBA")
        board = _checkerboard(rgba.width, rgba.height)
        board.paste(rgba, (0, 0), rgba)  # alpha-composite the subject over it
        img = board
    return ImageTk.PhotoImage(img)
