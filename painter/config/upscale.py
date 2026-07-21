"""Upscale (owner's #13) — Real-ESRGAN via the standalone ncnn-vulkan
binary, plus the gate that decides which images qualify.
"""

from .paths import PROJECT_ROOT

# Real-ESRGAN via the standalone realesrgan-ncnn-vulkan Windows
# binary. It lives under tools/realesrgan/ (gitignored, downloaded
# on first use from the official GitHub release).
TOOLS_DIR = PROJECT_ROOT / "tools"
UPSCALE_DIR = TOOLS_DIR / "realesrgan"
UPSCALE_EXE_NAME = "realesrgan-ncnn-vulkan.exe"
UPSCALE_ZIP_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
)
# Model (owner research 2026-07-21): the anime-6B net is ART-TUNED for
# flat-colour / cell-shaded illustration — this project's stained-glass
# rondels and badges — where the general-purpose x4plus over-smooths fine
# linework. A/B-verified live (realesrgan-ncnn-vulkan -n <model> -s 4) on
# a real 592x592 output (a Greek-pantheon rondel): x4plus-anime showed
# visibly crisper eye/hair/line detail, higher edge energy (Laplacian
# variance ~328 vs ~264), no colour shift (<1/255 mean RGB delta) or
# banding regression, a smaller PNG, and ran ~2.4x faster (3.3s vs 8.0s).
# Flip back to "realesrgan-x4plus" if a future asset style suits the
# smoother general-purpose net better.
UPSCALE_MODEL = "realesrgan-x4plus-anime"
# Gating (owner 2026-07-19, four editable params at the ENGINE level —
# painter/upscale.py's upscale_if_small signature/defaults are UNCHANGED
# by the GUI rework). An image qualifies ONLY if its aspect ratio W/H is
# within [UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX] (the circular/badge
# class) AND (W < UPSCALE_MIN_WIDTH OR H < UPSCALE_MIN_HEIGHT); then it
# is upscaled (native 4x + LANCZOS, aspect preserved) so W >=
# UPSCALE_MIN_WIDTH and H >= UPSCALE_MIN_HEIGHT. The defaults (800 / 800
# / 0.9 / 1.1) are the old min_px=800 + aspect_tol=0.1 behaviour.
#
# GUI rework Phase 6: the GUI no longer exposes min_width/min_height as
# TWO separate fields — a single min-SIDE spinner drives both (see
# UPSCALE_MIN_SIDE_DEFAULT below), and the aspect band is authored via
# an embedded FilterEditor condition instead of dedicated aspect-from/
# aspect-to fields (gui.py's AgentPanel/UpscaleParamsDialog and
# gui._upscale_params_from_side_and_filter). These four stay the
# ENGINE's own defaults, read by upscale_if_small's signature, main.py's
# CLI, and the GUI's migration of an owner's pre-Phase-6 settings.json.
UPSCALE_MIN_WIDTH = 800
UPSCALE_MIN_HEIGHT = 800
UPSCALE_ASPECT_MIN = 0.9
UPSCALE_ASPECT_MAX = 1.1
# GUI spinner step for the upscale gate's min-side field (Rule #4).
UPSCALE_MINDIM_STEP = 50  # min-side spinner step (px)
# GUI rework Phase 6: the per-agent AND standalone upscale gate collapse
# min WIDTH + min HEIGHT into ONE min-SIDE spinner (both axes must reach
# the same minimum now, gated separately by an embedded FilterEditor —
# see gui.py's AgentPanel/UpscaleParamsDialog and
# gui._upscale_params_from_side_and_filter). This is that spinner's seed
# default; reuses UPSCALE_MIN_WIDTH's value (== UPSCALE_MIN_HEIGHT
# already, by design) so the shipped default behaves byte-identically
# to the old four-field gate.
UPSCALE_MIN_SIDE_DEFAULT = UPSCALE_MIN_WIDTH
