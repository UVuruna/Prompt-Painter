"""Icon loading (SVG-first via QtSvg, PNG fallback) and the Day/Night
switch's hand-rendered art: anti-aliased sun/moon knobs (radial-
gradient discs, moon craters + terminator shading + surface mottling)
and the track-pill SVGs, all built on the same SVG->PIL rasterizer.

Split out of gui/__init__.py (Rule #3, god-file refactor step 2/8) —
the toolkit's LEAF module: no dependency on any other ``gui``
submodule."""

from __future__ import annotations

import io
import math
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from painter.config import (
    PROJECT_ROOT,
    SWITCH_COVER_ICON_FRAC,
    SWITCH_COVER_ICON_SS,
    SWITCH_CRATER,
    SWITCH_CRATERS,
    SWITCH_CRATER_RIM,
    SWITCH_CRATER_RIM_ALPHA,
    SWITCH_CRATER_RIM_ARC_DEG,
    SWITCH_CRATER_RIM_FRAC,
    SWITCH_KNOB_HILIGHT,
    SWITCH_MOON_CENTER,
    SWITCH_MOON_DARK_FLOOR,
    SWITCH_MOON_EDGE,
    SWITCH_MOON_LIGHT_DIR,
    SWITCH_MOON_NOISE_AMPL,
    SWITCH_MOON_NOISE_CELLS,
    SWITCH_MOON_NOISE_SEED,
    SWITCH_MOON_TERMINATOR_SOFT,
    SWITCH_SUN_CELL_SCALE,
    SWITCH_SUN_CENTER,
    SWITCH_SUN_EDGE,
    SWITCH_SUN_GLOW,
    SWITCH_SUN_GLOW_ALPHA,
    SWITCH_SUN_GLOW_BLUR,
    SWITCH_SUN_GLOW_SCALE,
    SWITCH_SUPERSAMPLE,
    THEMES,
)


# button icons — SVG-first (the owner's assets/icons/*.svg), rasterized
# through Qt's QSvgRenderer (PySide6, already a monorepo build dep) at
# 4x and LANCZOS-downscaled for crispness; PNG is the fallback for
# icons with no svg (web, ai) and for svgs Qt cannot render (see
# _QT_UNSUPPORTED_SVG). Resolved beside gui.py, never the CWD.
ICON_DIR = PROJECT_ROOT / "assets" / "icons"
ICON_TARGET_PX = 20  # max icon side inside a button / beside a switch
SVG_OVERSAMPLE = 4  # rasterize at 4x, then LANCZOS down

# QtSvg implements the SVG Tiny profile: clipPath/mask/filter (typical
# of Illustrator raster-trace exports like gemini.svg, 12 embedded
# rasters under 28 clipPaths) render as garbage — such files need a
# pre-rasterized .png sibling (gemini.png was rendered once from the
# svg via chromium, transparent, 512 px).
_QT_UNSUPPORTED_SVG = (b"<clipPath", b"<mask", b"<filter")

# CTk widgets show CTkImage (PIL-backed, smooth downscale) — cached per
# (name, size) for the whole process so every widget reuses one
# instance per icon.
_ICONS: dict[tuple[str, int], ctk.CTkImage] = {}

# QSvgRenderer needs a live QGuiApplication; created lazily on the
# first svg icon and kept for the whole process (never exec()-ed — it
# only serves offscreen painting, tkinter keeps the event loop).
_QT_APP = None

# the site logos (assets/icons stems) now live in config.JOB_LOGO —
# one home shared by the agent panels, dashboard panels and buttons.



def _svg_to_pil(path: Path, target_px: int) -> Image.Image:
    """Rasterize one SVG via QSvgRenderer: aspect-fit ``target_px`` on
    the longer side, rendered at SVG_OVERSAMPLE x and LANCZOS-downscaled
    so ~20 px icons stay crisp."""
    global _QT_APP
    from PySide6.QtCore import QBuffer, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    if _QT_APP is None:
        _QT_APP = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"unrenderable SVG: {path}")
    base = renderer.defaultSize()
    scale = target_px / max(base.width(), base.height())
    final = (
        max(round(base.width() * scale), 1),
        max(round(base.height() * scale), 1),
    )
    qimg = QImage(
        final[0] * SVG_OVERSAMPLE, final[1] * SVG_OVERSAMPLE,
        QImage.Format.Format_ARGB32,
    )
    qimg.fill(Qt.GlobalColor.transparent)
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    qimg.save(buffer, "PNG")
    pil = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")
    return pil.resize(final, Image.LANCZOS)


def icon(name: str, size: int = ICON_TARGET_PX) -> ctk.CTkImage:
    """The named icon, loaded once per (name, size) and scaled to fit.

    ``name.svg`` wins when Qt can render it; ``name.png`` covers the
    rest (web/ai have no svg; gemini.svg needs its pre-rasterized
    sibling). A missing/unrenderable icon is a loud error (root
    Rule #1) — no silent icon-less fallback.
    """
    key = (name, size)
    if key not in _ICONS:
        svg_path = ICON_DIR / f"{name}.svg"
        png_path = ICON_DIR / f"{name}.png"
        svg_ok = svg_path.is_file() and not any(
            tag in svg_path.read_bytes() for tag in _QT_UNSUPPORTED_SVG
        )
        if svg_ok:
            img = _svg_to_pil(svg_path, size)
        elif png_path.is_file():
            img = Image.open(png_path)
            scale = min(size / max(img.width, img.height), 1.0)
            img = img.convert("RGBA").resize(
                (
                    max(round(img.width * scale), 1),
                    max(round(img.height * scale), 1),
                ),
                Image.LANCZOS,
            )
        elif svg_path.is_file():
            raise FileNotFoundError(
                f"GUI icon {svg_path} uses SVG features QtSvg cannot"
                " render (clipPath/mask/filter) and has no .png sibling"
                " — pre-rasterize it once (e.g. via a browser) and save"
                f" it as {png_path}"
            )
        else:
            raise FileNotFoundError(
                f"GUI icon missing: {svg_path} / {png_path}"
            )
        _ICONS[key] = ctk.CTkImage(
            light_image=img, dark_image=img, size=img.size
        )
    return _ICONS[key]



# --- Day/Night switch art — anti-aliased PIL images (owner 2026-07-18)
# tkinter Canvas has no anti-aliasing, so the switch composites PIL
# images instead of raw ovals: the TWO track pills come straight from the
# owner's website SVGs (reusing the _svg_to_pil path above), the SUN/MOON
# knobs are rendered here as RGBA discs with a radial gradient, at
# SWITCH_SUPERSAMPLE x the final size then LANCZOS-downscaled for smooth
# edges. All four are built ONCE per switch (the switch is a fixed size —
# it does not follow the font zoom) and held on the widget.


def _radial_disc(
    px: int, center_hex: str, edge_hex: str, hilite: tuple[float, float]
) -> Image.Image:
    """A supersampled RGBA disc (``px`` square): a radial gradient from
    ``center_hex`` at the ``hilite`` point (fraction of the box) to
    ``edge_hex`` at the rim, opaque inside the inscribed circle and fully
    transparent outside. Rendered at native ``px`` — the caller LANCZOS-
    downscales the whole knob so the rim anti-aliases smoothly."""
    import numpy as np

    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32)
    r = px / 2.0
    hx, hy = hilite[0] * px, hilite[1] * px
    # distance from the highlight, normalised so the farthest rim point
    # (opposite the highlight) maps to 1.0 — keeps the ramp inside [0, 1]
    dist = np.sqrt((xx - hx) ** 2 + (yy - hy) ** 2)
    far = r + np.sqrt((hx - r) ** 2 + (hy - r) ** 2)
    t = np.clip(dist / far, 0.0, 1.0)[..., None]
    c0 = np.array(ImageColor.getrgb(center_hex), np.float32)
    c1 = np.array(ImageColor.getrgb(edge_hex), np.float32)
    rgb = c0 * (1.0 - t) + c1 * t
    # circular alpha mask (hard here; the downscale smooths the rim)
    dc = np.sqrt((xx - r + 0.5) ** 2 + (yy - r + 0.5) ** 2)
    alpha = np.where(dc <= r, 255.0, 0.0)[..., None]
    out = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _render_moon_knob(d_px: int, ss: int) -> Image.Image:
    """The MOON — a real moon, not a flat disc (owner 2026-07-20).

    Three layers over the silver radial-gradient sphere, all driven by
    the SWITCH_MOON_* / SWITCH_CRATER* config constants:
      * 7 CRATERS of varied sizes (darker floors), each with a lit RIM
        ARC on the side facing the incoming light;
      * TERMINATOR shading — brightness ramps from the lit limb (the
        SWITCH_MOON_LIGHT_DIR side) down to SWITCH_MOON_DARK_FLOOR on
        the far limb across a soft smoothstep band, darkening crater
        floors and rims with the surface so the sphere reads as lit
        from one side;
      * subtle surface MOTTLING — a low-res value-noise grid (FIXED
        seed, so the moon is identical every build) bicubic-upscaled
        over the disc, ± SWITCH_MOON_NOISE_AMPL brightness steps.
    ``d_px`` = final diameter, ``ss`` = supersample factor (rendered at
    ss x, LANCZOS-downscaled like every knob)."""
    import numpy as np

    s = d_px * ss
    disc = _radial_disc(
        s, SWITCH_MOON_CENTER, SWITCH_MOON_EDGE, SWITCH_KNOB_HILIGHT
    )
    draw = ImageDraw.Draw(disc)
    crater = (*ImageColor.getrgb(SWITCH_CRATER), 255)
    # the rims live on their own layer and alpha-BLEND onto the disc —
    # drawing a translucent fill straight into the RGBA disc would
    # REPLACE the alpha (a see-through ring), and a solid near-white
    # arc read as a pac-man ring instead of a subtle lit rim
    rims = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    rim_draw = ImageDraw.Draw(rims)
    rim = (*ImageColor.getrgb(SWITCH_CRATER_RIM), SWITCH_CRATER_RIM_ALPHA)
    lx, ly = SWITCH_MOON_LIGHT_DIR
    # PIL arc degrees (x right, y down, clockwise from 3 o'clock): the
    # rim arc is centred on the direction the light comes FROM
    light_deg = math.degrees(math.atan2(ly, lx))
    half_arc = SWITCH_CRATER_RIM_ARC_DEG / 2
    for cf, cxf, cyf in SWITCH_CRATERS:
        cd = s * cf
        ccx, ccy = cxf * s, cyf * s
        box = [ccx - cd / 2, ccy - cd / 2, ccx + cd / 2, ccy + cd / 2]
        draw.ellipse(box, fill=crater)
        rim_draw.arc(
            box, start=light_deg - half_arc, end=light_deg + half_arc,
            fill=rim, width=max(round(cd * SWITCH_CRATER_RIM_FRAC), ss),
        )
    disc.alpha_composite(rims)
    # terminator shading x mottling on the RGB channels (alpha untouched)
    arr = np.asarray(disc).astype(np.float32)
    r = s / 2.0
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    nx, ny = (xx - r + 0.5) / r, (yy - r + 0.5) / r
    # projection onto the light direction: +1 = the lit limb, -1 = far
    proj = (nx * lx + ny * ly) / math.hypot(lx, ly)
    soft = SWITCH_MOON_TERMINATOR_SOFT
    u = np.clip((proj + soft) / (2.0 * soft), 0.0, 1.0)
    u = u * u * (3.0 - 2.0 * u)  # smoothstep across the terminator band
    shade = SWITCH_MOON_DARK_FLOOR + (1.0 - SWITCH_MOON_DARK_FLOOR) * u
    rng = np.random.default_rng(SWITCH_MOON_NOISE_SEED)
    cells = rng.uniform(-1.0, 1.0, (SWITCH_MOON_NOISE_CELLS,) * 2)
    noise = Image.fromarray(
        ((cells + 1.0) * 127.5).astype(np.uint8), "L"
    ).resize((s, s), Image.BICUBIC)
    mottle = (
        np.asarray(noise).astype(np.float32) / 127.5 - 1.0
    ) * SWITCH_MOON_NOISE_AMPL
    arr[..., :3] = np.clip(
        arr[..., :3] * shade[..., None] + mottle[..., None], 0.0, 255.0
    )
    disc = Image.fromarray(arr.astype(np.uint8), "RGBA")
    return disc.resize((d_px, d_px), Image.LANCZOS)


def _render_sun_knob(d_px: int, ss: int) -> Image.Image:
    """The SUN: a gold radial-gradient sphere over a soft blurred gold
    glow. The image is SWITCH_SUN_CELL_SCALE x the knob so the glow has
    room to fade; the sun disc sits centred. ``d_px`` = knob diameter."""
    cell = round(d_px * SWITCH_SUN_CELL_SCALE)
    s = cell * ss
    # glow: a low-alpha gold disc behind, GaussianBlur-ed to a soft halo
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = d_px * SWITCH_SUN_GLOW_SCALE * ss
    gc = s / 2.0
    ImageDraw.Draw(glow).ellipse(
        [gc - gd / 2, gc - gd / 2, gc + gd / 2, gc + gd / 2],
        fill=(*ImageColor.getrgb(SWITCH_SUN_GLOW), SWITCH_SUN_GLOW_ALPHA),
    )
    glow = glow.filter(
        ImageFilter.GaussianBlur(SWITCH_SUN_GLOW_BLUR * d_px * ss)
    )
    disc = _radial_disc(
        d_px * ss, SWITCH_SUN_CENTER, SWITCH_SUN_EDGE, SWITCH_KNOB_HILIGHT
    )
    off = round((s - d_px * ss) / 2)
    glow.alpha_composite(disc, (off, off))
    return glow.resize((cell, cell), Image.LANCZOS)


def _render_theme_cover_icon(target_name: str, min_dim: int) -> Image.Image:
    """The BIG centred icon that rides the theme cross-fade cover: the
    SUN of the theme being switched TO (day) or the MOON (night), the
    SAME anti-aliased PIL renderers as the switch knob, sized to
    ``SWITCH_COVER_ICON_FRAC`` of the window's min dimension. RGBA with
    transparent surroundings so it composites cleanly onto the snapshot
    (owner 2026-07-19)."""
    d = max(round(min_dim * SWITCH_COVER_ICON_FRAC), 1)
    ss = SWITCH_COVER_ICON_SS
    if THEMES[target_name]["switch_on"]:   # going to day -> the sun
        return _render_sun_knob(d, ss)
    return _render_moon_knob(d, ss)        # going to night -> the moon


def _render_switch_track(stem: str, w: int, h: int) -> Image.Image:
    """One track pill: the owner's website switch SVG (in assets/icons),
    rasterized anti-aliased through the icon SVG->PIL path and sized to
    the exact pill box. A missing SVG is a loud error (Rule #1)."""
    svg_path = ICON_DIR / f"{stem}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(
            f"Day/Night switch track SVG missing: {svg_path}"
        )
    pil = _svg_to_pil(svg_path, w)
    if pil.size != (w, h):
        pil = pil.resize((w, h), Image.LANCZOS)
    return pil

