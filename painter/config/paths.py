"""Project paths, CDP/Chrome launch config, output layout, settings path.

Everything here is a leaf: no dependency on any other config submodule.
"""

import re
from pathlib import Path

# ═══════════════════════════ PROJECT ROOT ═══════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ═════════════════════ CDP ATTACHMENT / CHROME LAUNCH ════════════════
# --- CDP attachment / Chrome launch ----------------------------------

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Where chrome.exe usually lives; the launcher tries these in order.
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# Chrome 136+ refuses --remote-debugging-port on the DEFAULT profile,
# so PromptPainter launches Chrome with its own profile folder. The
# owner logs in ONCE there (Google + OpenAI); sessions persist.
CHROME_PROFILE_DIR = PROJECT_ROOT / "chrome-profile"

# launch -> the CDP endpoint must answer within this window
CHROME_LAUNCH_TIMEOUT_S = 30.0

# ═══════════════════════════ OUTPUT LAYOUT ═══════════════════════════
# --- Output ----------------------------------------------------------

# EVERYTHING THE PROGRAM PRODUCES LIVES UNDER ONE ROOT (owner
# 2026-08-04): the generated images AND the generated prompt sheets.
# One folder to gitignore, one folder to back up, one folder to empty
# — instead of a scatter of product dirs at the project root, which is
# also what made a generated .md read as project documentation and
# fail THE DOCS LAW. Both defaults below hang off it; each is still
# freely overridable per run in the GUI (and by --out on the CLI).
GENERATED_ROOT = PROJECT_ROOT / "output"

# The out/ folder MIRRORS the DOMY assets/ tree so the owner can copy
# its whole content straight into assets/ (owner 2026-07-18). Sheets
# carry site-agnostic FULL drop paths ("assets/calendars/emotions/
# Love.png"); the site lands as the TERMINAL FILENAME SUFFIX (DOMY
# RESTRUCTURE 2026-07-22 — source folders are dead, `<Figure>[_vN]_
# <src>.png` with src ∈ {gem, gpt, api}):
#     assets/<rest>/<File>.png  ->  <out>/<rest>/<File>_<sfx>.png
# so the out/ tree is byte-for-byte the shape assets/ expects. Only
# legacy relative drops keep the old folder layouts. Run state and
# reports live OUT of the copyable tree, under <out>/_state/<site>/;
# backup variants land under <out>/EXTRA/.
DEFAULT_OUT_DIR = GENERATED_ROOT / "images"
# where the New Collection (AI) wizard saves its sheets — a SIBLING of
# the images, never inside them: the images tree is copy-ready into
# DOMY's assets/, and a sheets/ folder in there would travel with it.
DEFAULT_SHEETS_DIR = GENERATED_ROOT / "sheets"
STATE_DIRNAME = "_state"
REPORT_SUFFIX = "_report.txt"

# site key -> the DOMY filename suffix (source ALWAYS last in the
# stem). THE one authority — every image generator MUST register its
# suffix here before generating (binding rule + registry table:
# CLAUDE.md "The Generator Suffix Registry"). "api_image" is the
# Gemini image API job; future API generators each get their OWN
# suffix — the suffix names the generator, never a model version.
SITE_FILE_SUFFIX = {"chatgpt": "_gpt", "gemini": "_gem", "api_image": "_api"}


def dest_for(drop_path: str, site_key: str) -> str:
    """The save path (relative to the out base) for one drop path."""
    parts = drop_path.split("/")
    suffix = SITE_FILE_SUFFIX[site_key]
    if parts[0] == "assets" and len(parts) >= 3:
        name = parts[-1]
        stem, dot, ext = name.rpartition(".")
        name = f"{stem}{suffix}.{ext}" if dot else f"{name}{suffix}"
        return "/".join([*parts[1:-1], name])
    return "/".join([site_key, drop_path])


def versioned_dest_for(
    drop_path: str, site_key: str, out_base: Path
) -> str:
    """The dest (same rel form as ``dest_for``) for a NEW VERSION of
    an image whose canonical file already exists on disk.

    Re-ticking a done item never overwrites it (owner 2026-07-27): the
    redo lands as the next ``_vN`` sibling per the DOMY rotation
    convention — ``<File>[_vN]_<sfx>.png``, the ``_vN`` slotted BEFORE
    the terminal generator suffix; the canonical file IS version 1 and
    the first redo is ``_v2``. Scans the dest folder for existing
    version siblings and returns LAST + 1 ("ako je poslednja v4, on
    pravi v5" — gaps never matter), tolerant of the owner's irregular
    ``_v``/``_v1`` forms (both read as version 1, like DOMY's own
    rotation discovery). A legacy (non-assets) dest, whose filename
    carries no generator suffix, versions before the extension
    instead.
    """
    rel = dest_for(drop_path, site_key)
    folder, _, name = rel.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem = name
    suffix = SITE_FILE_SUFFIX[site_key]
    tail = suffix if stem.endswith(suffix) else ""
    base = stem[: -len(tail)] if tail else stem
    pattern = re.compile(
        re.escape(base) + r"_v(\d*)" + re.escape(tail)
        + (re.escape(f".{ext}") if dot else "") + r"$"
    )
    last = 1  # the canonical file is version 1
    dest_dir = out_base / folder if folder else out_base
    if dest_dir.is_dir():
        for existing in dest_dir.iterdir():
            match = pattern.fullmatch(existing.name)
            if match:
                last = max(last, int(match.group(1) or 1))
    versioned = f"{base}_v{last + 1}{tail}" + (f".{ext}" if dot else "")
    return f"{folder}/{versioned}" if folder else versioned


# ═════════════════════════ SETTINGS PERSISTENCE ══════════════════════
# --- Settings persistence (owner's #9) -------------------------------

# The GUI's remembered choices; JSON at the project root, gitignored.
# What goes in the dict is the GUI's business — this is just the home.
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
