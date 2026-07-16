"""PromptPainter configuration — every tunable value lives here.

Selectors rot with every site reskin: each DOM hook below is a tuple
of fallbacks tried in order, and when none match the driver FAILS
LOUDLY (root Rule #1) instead of guessing.
"""

from dataclasses import dataclass

# --- CDP attachment -------------------------------------------------

# Chrome must run with: chrome.exe --remote-debugging-port=9222
CDP_URL = "http://localhost:9222"

# --- Output ----------------------------------------------------------

DEFAULT_OUT_DIR = "out"
# Sidecar run state: out/<sheet-stem>.progress.json
PROGRESS_SUFFIX = ".progress.json"

# --- The sheet contract ----------------------------------------------

# The arrow line must name a file with one of these extensions.
IMAGE_EXTENSIONS = (".png",)

# A bold span matching this marks an entry (or a whole section) as
# skipped — logged, never generated.
SKIP_MARKER_PATTERN = r"\bREUSE\b|\bSUPERSEDED\b|\bDO[\s-]+NOT[\s-]+GENERATE\b"


# --- Timing ----------------------------------------------------------

@dataclass(frozen=True)
class Timing:
    """All waits and paces, in seconds."""

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
    # substring of the tab URL used to find the already-open tab
    url_fragment: str
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
        url_fragment="chatgpt.com",
        prompt_box=(
            "#prompt-textarea",
            "div.ProseMirror[contenteditable='true']",
        ),
        send_button=(
            'button[data-testid="send-button"]',
            'button[aria-label*="Send" i]',
        ),
        busy_signal=(
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop" i]',
        ),
        response_container=(
            'article[data-testid^="conversation-turn"]',
            "article",
        ),
        result_image=(
            'img[alt*="Generated" i]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
            'img[src*="oaiusercontent"]',
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
        url_fragment="gemini.google.com",
        prompt_box=(
            "rich-textarea div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
        ),
        send_button=(
            'button[aria-label*="Send" i]',
            "button.send-button",
        ),
        busy_signal=(
            'button[aria-label*="Stop" i]',
            "button.send-button.stop",
            'mat-icon[data-mat-icon-name="stop"]',
        ),
        response_container=(
            "model-response",
            "message-content",
        ),
        result_image=(
            "generated-image img",
            "single-image img",
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
