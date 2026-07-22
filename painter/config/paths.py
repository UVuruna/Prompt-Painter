"""Project paths, CDP/Chrome launch config, output layout, settings path.

Everything here is a leaf: no dependency on any other config submodule.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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

# --- Output ----------------------------------------------------------

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
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"
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


# --- Settings persistence (owner's #9) -------------------------------

# The GUI's remembered choices; JSON at the project root, gitignored.
# What goes in the dict is the GUI's business — this is just the home.
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
