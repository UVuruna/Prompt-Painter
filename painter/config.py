"""PromptPainter configuration — every tunable value lives here.

Selectors rot with every site reskin: each DOM hook below is a tuple
of fallbacks tried in order, and when none match the driver FAILS
LOUDLY (root Rule #1) instead of guessing.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --- small formatters (shared by the runner and the GUI) -------------

def fmt_duration(seconds: float) -> str:
    """A short human duration: '3m 12s', '48s'."""
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def fmt_size(num_bytes: int) -> str:
    """A short human file size: '1.4 MB', '812 KB', '70 B'."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / 1_048_576:.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"

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
# carry site-agnostic FULL drop paths ("assets/emblem/mood/Glory.png");
# the site is injected after the category:
#     assets/<category>/<rest>  ->  <out>/<category>/<site>/<rest>
# Legacy relative drops keep the old layout: <out>/<site>/<drop>.
# Run state and reports live OUT of the copyable tree, under
# <out>/_state/<site>/; backup variants land under <out>/EXTRA/.
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"
STATE_DIRNAME = "_state"
PROGRESS_SUFFIX = ".progress.json"
REPORT_SUFFIX = "_report.txt"


def dest_for(drop_path: str, site_key: str) -> str:
    """The save path (relative to the out base) for one drop path."""
    parts = drop_path.split("/")
    if parts[0] == "assets" and len(parts) >= 3:
        category, rest = parts[1], parts[2:]
        return "/".join([category, site_key, *rest])
    return "/".join([site_key, drop_path])

# --- The sheet contract ----------------------------------------------

# The arrow line must name a file with one of these extensions.
IMAGE_EXTENSIONS = (".png",)

# A bold span matching this marks an entry (or a whole section) as
# skipped — logged, never generated.
SKIP_MARKER_PATTERN = r"\bREUSE\b|\bSUPERSEDED\b|\bDO[\s-]+NOT[\s-]+GENERATE\b"

# --- Postprocess: background removal + crop (owner workflow step 6) --

# painter/postprocess.py runs over every saved image; the two steps
# are COMPOSABLE (owner's #7): remove_background auto-detects per
# file (already-transparent -> nothing, white/black cleared,
# ambiguous -> unclear, left untouched); crop_transparent autocrops
# a transparent image to its content bounding box.
CROP_MARGIN_PX = 4  # safety margin kept around the content box
CROP_ALPHA_THRESH = 8  # alpha below this counts as empty (feather ring)


# --- Upscale (owner's #13) -------------------------------------------

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
UPSCALE_MODEL = "realesrgan-x4plus"
# Gating (owner 2026-07-18): an image qualifies ONLY if its aspect
# ratio W/H is within 1 +- UPSCALE_ASPECT_TOL (the circular/badge
# class) AND W or H is below UPSCALE_MIN_PX; then it is upscaled so
# NO dimension stays below UPSCALE_MIN_PX (aspect preserved).
UPSCALE_MIN_PX = 800
UPSCALE_ASPECT_TOL = 0.1


# --- Settings persistence (owner's #9) -------------------------------

# The GUI's remembered choices; JSON at the project root, gitignored.
# What goes in the dict is the GUI's business — this is just the home.
SETTINGS_PATH = PROJECT_ROOT / "settings.json"


# --- Prompt rules appended per site (owner 2026-07-17) ---------------

# The GUI shows ONE background dropdown PER SITE; the default
# selection is the site's default_background (ChatGPT transparent —
# it can do real alpha; Gemini white — the background fix clears it).
BACKGROUND_CHOICES = ("transparent", "white", "none")

_BACKGROUND_RULE = {
    "transparent": (
        "render on a fully TRANSPARENT background — a REAL alpha"
        " channel in the PNG, no backdrop of any kind; NEVER paint a"
        " fake gray-and-white checkerboard pattern as the background"
    ),
    "white": (
        "render on a PLAIN PURE WHITE background — flat white, no"
        " gradients, no vignette, no backdrop scenery"
    ),
    "none": None,
}

# Extra laws forced into EVERY prompt of a site. Gemini's weaker
# model drifts (wrong ratios, glossy reflections under the subject —
# the rondel_Dawn / rondel_Shield case), so it gets hard rules.
SITE_PROMPT_RULES = {
    "chatgpt": (),
    "gemini": (
        "absolutely NO reflections — no mirror effect, no glossy"
        " floor, no reflective surface under or around the subject",
    ),
}

# The aspect-ratio law DEPENDS ON THE IMAGE (owner 2026-07-17; since
# 2026-07-18 sent to BOTH sites — ChatGPT drifts too): most plates
# are badges/rondels/medallions -> a perfect square, but the
# church-window lancets are clearly taller than wide. The rule is
# picked from the PROMPT TEXT itself — first pattern that matches
# wins; the default is the square.
ASPECT_RULES = (
    (
        re.compile(r"\bTALL\b|\blancet\b", re.IGNORECASE),
        "ASPECT RATIO tall PORTRAIT — the image must be clearly"
        " TALLER than it is wide (around 2:3), matching the tall"
        " window shape described; never landscape, never square",
    ),
)
ASPECT_DEFAULT = (
    "ASPECT RATIO exactly 1:1 — a perfect square image"
)


def _aspect_rule(prompt_text: str) -> str:
    for pattern, rule in ASPECT_RULES:
        if pattern.search(prompt_text):
            return rule
    return ASPECT_DEFAULT


def prompt_suffix(site_key: str, background: str, prompt_text: str = "") -> str:
    """The rule block appended to one prompt of one site."""
    rules = [_aspect_rule(prompt_text)]
    bg_rule = _BACKGROUND_RULE[background]
    if bg_rule:
        rules.append(bg_rule)
    rules.extend(SITE_PROMPT_RULES[site_key])
    if not rules:
        return ""
    if len(rules) == 1:
        return f"\n\nIMPORTANT: {rules[0]}."
    numbered = " ".join(
        f"{n}) {rule}." for n, rule in enumerate(rules, start=1)
    )
    return f"\n\nIMPORTANT — follow ALL rules strictly: {numbered}"


# --- Safer-retry preamble (opt-in, owner 2026-07-17) -----------------

# When a SAFETY refusal is detected and "safer retry" is on, the same
# prompt is re-sent ONCE with this preamble prepended. It is an honest
# REFRAMING of legitimate allegorical art (no real people, symbolic,
# non-graphic) — not a way to force genuinely disallowed content. If
# it still refuses, the item is left REFUSED for the owner to rework.
SAFER_PREAMBLE = (
    "This is a purely SYMBOLIC stained-glass ALLEGORY of an abstract"
    " idea for a decorative church-window art set. There are NO real"
    " or identifiable people, no realism and nothing graphic — only"
    " simplified emblematic figures rendered as coloured glass and"
    " lead. Depict the CONCEPT itself (an emotion, virtue or vice),"
    " never a literal act; keep every element tasteful, non-violent"
    " and non-graphic. Treat any strong phrase below as a gentle"
    " metaphor, not a literal instruction.\n\n"
)


# --- Timing ----------------------------------------------------------

@dataclass(frozen=True)
class Timing:
    """All waits and paces, in seconds."""

    # human-like hesitation between UI actions (click box -> paste,
    # paste -> send ...): a random delay drawn from this range, like
    # a person doing Ctrl+V and then Enter
    action_delay_min_s: float = 0.2
    action_delay_max_s: float = 0.6
    # a required element (prompt box, send button) must appear;
    # SPAs morph elements a beat after input events, so lookups
    # poll instead of failing on a one-shot snapshot
    selector_timeout_s: float = 10.0
    # submit clicked -> the busy signal (stop button) must appear
    busy_appear_timeout_s: float = 30.0
    # no busy signal after this long -> click send / press Enter again
    # (the send button is sometimes momentarily blocked)
    send_retry_after_s: float = 5.0
    # busy signal seen -> its disappearance (the done edge), hard cap
    generation_timeout_s: float = 420.0
    # done edge -> a real (non-placeholder) result <img> src
    image_ready_timeout_s: float = 90.0
    # DOM polling step
    poll_interval_s: float = 0.5
    # "still generating..." log cadence during long waits
    progress_log_interval_s: float = 15.0
    # polite pause between prompts (image quotas are real): a RANDOM
    # duration drawn uniformly from [min, max], fractional seconds
    # included (e.g. 12.56s) — less robotic pacing
    pause_min_s: float = 30.0
    pause_max_s: float = 75.0


TIMING = Timing()

# An <img> narrower than this is a placeholder, not a generated image.
MIN_IMAGE_PX = 64


# --- Quota reset time (owner's #2) -----------------------------------

# ChatGPT's live quota message names the wait ("... when the limit
# resets in 27 minutes" / "in 14 hours"); Serbian-locale variants
# phrase it as "za 27 minuta" / "za 14 sati". Each pattern captures
# ONE number; the value is multiplied by the unit's seconds. Matches
# are summed so "in 2 hours" + a minutes phrase both count; an
# unparseable message yields None (the caller still stops — the
# reset time is a bonus, never a requirement).
QUOTA_RESET_PATTERNS: tuple[tuple[re.Pattern, float], ...] = (
    (re.compile(r"\bin\s+(\d+)\s*h(?:ours?|rs?)?\b", re.IGNORECASE), 3600.0),
    (re.compile(r"\bin\s+(\d+)\s*min(?:ute)?s?\b", re.IGNORECASE), 60.0),
    # Serbian: "za 14 sati" / "za 2 sata" / "za 27 minuta" / "za 1 minut"
    (re.compile(r"\bza\s+(\d+)\s*sat(?:i|a)?\b", re.IGNORECASE), 3600.0),
    (re.compile(r"\bza\s+(\d+)\s*min(?:ut)?a?\b", re.IGNORECASE), 60.0),
)


def parse_quota_reset(text: str) -> float | None:
    """Seconds until the quota resets, read from a quota response.

    None when no pattern matches — the message carried no parseable
    wait time (e.g. Gemini's "as soon as your limit resets").
    """
    total = 0.0
    found = False
    for pattern, unit_s in QUOTA_RESET_PATTERNS:
        match = pattern.search(text)
        if match:
            total += float(match.group(1)) * unit_s
            found = True
    return total if found else None


# --- Site DOM states (ONE config block, with fallbacks) --------------

@dataclass(frozen=True)
class SiteConfig:
    """The DOM hooks the driver watches on one site."""

    name: str
    # the tab the launcher opens
    url: str
    # substring of the tab URL used to find the already-open tab
    url_fragment: str
    # the BACKGROUND_SUFFIXES key used when the mode is 'auto'
    default_background: str
    # the contenteditable prompt box
    prompt_box: tuple[str, ...]
    # the idle send button
    send_button: tuple[str, ...]
    # visible only WHILE generating; its disappearance is the done edge
    busy_signal: tuple[str, ...]
    # one response turn; the LAST match holds the result
    response_container: tuple[str, ...]
    # generated <img> nodes inside the last response container
    result_image: tuple[str, ...]
    # substrings marking a SAFETY refusal of ONE prompt — the item
    # is reported and skipped, the run continues (owner 2026-07-17)
    refusal_text_markers: tuple[str, ...]
    # substrings marking a quota/rate limit — TERMINAL for the whole
    # site: report and stop, never blind-retry
    quota_text_markers: tuple[str, ...]
    # the sidebar "New chat" control (owner captures 2026-07-18) —
    # clicked between collections/folders when the option is on
    new_chat: tuple[str, ...] = ()


SITES = {
    "chatgpt": SiteConfig(
        name="ChatGPT",
        url="https://chatgpt.com/",
        url_fragment="chatgpt.com",
        default_background="transparent",
        # Verified against the live DOM by the owner, 2026-07-17
        # (UV/ screenshots): the composer button keeps the stable id
        # #composer-submit-button and morphs by state — empty box =
        # "Start Voice", text = data-testid="send-button" /
        # aria-label="Send prompt", GENERATING = data-testid=
        # "stop-button" / aria-label="Stop answering". A response
        # turn is <section data-turn="assistant" data-testid=
        # "conversation-turn-N">; the generated image sits in
        # <div id="image-<uuid>" class="group/imagegen-image"> as
        # <img alt="Generated image: ..." src="https://chatgpt.com/
        # backend-api/estuary/content?id=...&sig=...">.
        prompt_box=(
            "#prompt-textarea",
            "div.ProseMirror[contenteditable='true']",
        ),
        send_button=(
            'button[data-testid="send-button"]',
            "#composer-submit-button",
            'button[aria-label*="Send" i]',
        ),
        busy_signal=(
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop answering" i]',
        ),
        response_container=(
            'section[data-turn="assistant"]',
            '[data-testid^="conversation-turn"][data-turn="assistant"]',
            'article[data-testid^="conversation-turn"]',
            "article",
        ),
        result_image=(
            'div[id^="image-"] img',
            'img[alt*="Generated image" i]',
            'img[src*="/backend-api/"]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_text_markers=(
            "can't create",
            "cannot create",
            "can't generate",
            "cannot generate",
            # live capture 2026-07-17: "We're so sorry, but the prompt
            # may violate our content policies. If you think we got it
            # wrong, please retry or edit your prompt." — "content
            # polic" catches both policy and policies
            "content polic",
            "may violate",
            "violate our",
            "retry or edit your prompt",
            "unable to create",
            "not able to create",
        ),
        quota_text_markers=(
            "reached your limit",
            "too many requests",
            "rate limit",
            "try again later",
            # live capture 2026-07-17: "You've hit the Plus plan limit
            # for image generations requests. You can create more images
            # when the limit resets in 14 hours ..."
            "plan limit",
            "limit resets",
            "generation limit",
            "image generation limit",
        ),
        new_chat=(
            'a[data-testid="create-new-chat-button"]',
            'a[href="/"][data-sidebar-item="true"]',
        ),
    ),
    "gemini": SiteConfig(
        name="Gemini",
        url="https://gemini.google.com/app",
        url_fragment="gemini.google.com",
        default_background="white",
        # Verified against the live DOM by the owner, 2026-07-17
        # (UV/Gemini screenshots): the prompt box is <rich-textarea>
        # holding div.ql-editor[contenteditable] ("Ask Gemini");
        # send and stop share ONE container, <div data-test-id=
        # "send-button-container"> > <gem-icon-button> — typing makes
        # it visible as aria-label="Send message", generating turns
        # it into class "stop" / aria-label="Stop response" with
        # mat-icon "stop". A response is <model-response>; the image
        # sits under generated-image > single-image >
        # button.image-button as <img class="image animate loaded"
        # alt=", AI generated" src="blob:https://gemini.google.com/...">.
        prompt_box=(
            "rich-textarea div.ql-editor[contenteditable='true']",
            "rich-textarea div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
        ),
        send_button=(
            'div[data-test-id="send-button-container"] button',
            'button[aria-label*="Send message" i]',
            'button[aria-label*="Send" i]',
        ),
        busy_signal=(
            'button[aria-label*="Stop response" i]',
            "gem-icon-button.stop button",
            'button[aria-label*="Stop" i]',
            'mat-icon[data-mat-icon-name="stop"]',
        ),
        response_container=(
            "model-response",
            "message-content",
        ),
        result_image=(
            "generated-image img",
            "single-image img",
            "button.image-button img",
            'img[alt*="AI generated" i]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_text_markers=(
            "can't create",
            "cannot create",
            "can't generate",
            "cannot generate",
            "unable to generate",
            "unsafe",
            # Gemini answers in the account's language — Serbian too
            "ne mogu da generi",
            "ne mogu da kreiram",
            "bezbednosn",
        ),
        quota_text_markers=(
            "quota",
            "limit reached",
            "too many requests",
            "rate limit",
            "try again later",
            # live capture 2026-07-17: "I can create more images as
            # soon as your limit resets. Check your usage in Settings."
            "limit resets",
            "your limit",
            "check your usage",
            "dostigli ste",
            "ograničenj",
        ),
        new_chat=(
            'a[aria-label="New chat"]',
            'gem-icon-button a[href="/app"]',
        ),
    ),
}

# When to open a fresh chat during a run (GUI dropdown / CLI flag):
# off = one long conversation per site; collection = a new chat after
# every finished collection; folder = also between folder groups
# INSIDE a collection (primary -> colored ...).
NEW_CHAT_CHOICES = ("off", "collection", "folder")
