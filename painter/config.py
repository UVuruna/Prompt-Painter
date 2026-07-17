"""PromptPainter configuration — every tunable value lives here.

Selectors rot with every site reskin: each DOM hook below is a tuple
of fallbacks tried in order, and when none match the driver FAILS
LOUDLY (root Rule #1) instead of guessing.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

# Images save DIRECTLY to <out>/<site>/<drop-path> (owner
# 2026-07-17: no approval step). Per-site sidecar state and the run
# report live beside them: <out>/<site>/<sheet-stem>.progress.json
# and <out>/<site>/<sheet-stem>_report.txt
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"
PROGRESS_SUFFIX = ".progress.json"
REPORT_SUFFIX = "_report.txt"

# --- The sheet contract ----------------------------------------------

# The arrow line must name a file with one of these extensions.
IMAGE_EXTENSIONS = (".png",)

# A bold span matching this marks an entry (or a whole section) as
# skipped — logged, never generated.
SKIP_MARKER_PATTERN = r"\bREUSE\b|\bSUPERSEDED\b|\bDO[\s-]+NOT[\s-]+GENERATE\b"

# --- Background fix (owner workflow step 5) --------------------------

# painter/bg_remove.py runs over every saved image and auto-detects —
# already-transparent images are skipped, white backgrounds (Gemini)
# are cleared, ambiguous ones are reported and left untouched.
BG_FIX_CROP = True  # autocrop to the visible subject after clearing


# --- Prompt rules appended per site (owner 2026-07-17) ---------------

# The GUI shows ONE background dropdown PER SITE; the default
# selection is the site's default_background (ChatGPT transparent —
# it can do real alpha; Gemini white — the background fix clears it).
BACKGROUND_CHOICES = ("transparent", "white", "none")

_BACKGROUND_RULE = {
    "transparent": (
        "render on a fully TRANSPARENT background (PNG with alpha"
        " channel, no backdrop of any kind)"
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

# Gemini's aspect-ratio law DEPENDS ON THE IMAGE (owner 2026-07-17):
# most plates are badges/rondels/medallions -> a perfect square, but
# the church-window lancets are clearly taller than wide. The rule is
# picked from the PROMPT TEXT itself — first pattern that matches
# wins; the default is the square.
GEMINI_ASPECT_RULES = (
    (
        re.compile(r"\bTALL\b|\blancet\b", re.IGNORECASE),
        "ASPECT RATIO tall PORTRAIT — the image must be clearly"
        " TALLER than it is wide (around 2:3), matching the tall"
        " window shape described; never landscape, never square",
    ),
)
GEMINI_ASPECT_DEFAULT = (
    "ASPECT RATIO exactly 1:1 — a perfect square image"
)


def _gemini_aspect_rule(prompt_text: str) -> str:
    for pattern, rule in GEMINI_ASPECT_RULES:
        if pattern.search(prompt_text):
            return rule
    return GEMINI_ASPECT_DEFAULT


def prompt_suffix(site_key: str, background: str, prompt_text: str = "") -> str:
    """The rule block appended to one prompt of one site."""
    rules = []
    if site_key == "gemini":
        rules.append(_gemini_aspect_rule(prompt_text))
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


# --- Timing ----------------------------------------------------------

@dataclass(frozen=True)
class Timing:
    """All waits and paces, in seconds."""

    # a required element (prompt box, send button) must appear;
    # SPAs morph elements a beat after input events, so lookups
    # poll instead of failing on a one-shot snapshot
    selector_timeout_s: float = 10.0
    # submit clicked -> the busy signal (stop button) must appear
    busy_appear_timeout_s: float = 20.0
    # busy signal seen -> its disappearance (the done edge), hard cap
    generation_timeout_s: float = 420.0
    # done edge -> a real (non-placeholder) result <img> src
    image_ready_timeout_s: float = 90.0
    # DOM polling step
    poll_interval_s: float = 0.5
    # "still generating..." log cadence during long waits
    progress_log_interval_s: float = 15.0
    # polite pause between prompts (image quotas are real)
    pause_between_prompts_s: float = 45.0


TIMING = Timing()

# An <img> narrower than this is a placeholder, not a generated image.
MIN_IMAGE_PX = 64


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
    # substrings that mark a no-image response as a TERMINAL
    # quota/refusal state (report and stop, never blind-retry)
    refusal_text_markers: tuple[str, ...]


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
            "content policy",
            "reached your limit",
            "try again later",
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
            "quota",
            "limit reached",
            "try again later",
            "unable to generate",
        ),
    ),
}
