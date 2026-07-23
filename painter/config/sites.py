"""Timing, per-site DOM state selectors, and the driving loop's small
tunables. Selectors rot with every site reskin — each DOM hook below is
a tuple of fallbacks tried in order, and when none match the driver
FAILS LOUDLY (root Rule #1) instead of guessing.
"""

from dataclasses import dataclass

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

# The GUI's Pause toggle (owner 2026-07-21) blocks the run loop (and the
# tool/AI-check worker loops) between items until Resume or Stop — the
# poll granularity of that wait. A plain top-level constant, not a
# Timing field: it is an internal wait-loop step, never a per-run/
# per-site tunable exposed in the UI (unlike Timing.pause_min_s/max_s,
# the random PACING wait between prompts — a different, existing
# feature that shares the word "pause" but not the mechanism).
PAUSE_POLL_INTERVAL_S = 0.5

# An <img> narrower than this is a placeholder, not a generated image.
MIN_IMAGE_PX = 64

# Owner 2026-07-21 (a live run stopped dead: "no selector for the send
# button matched within 10s ... site stopped" — a manual page REFRESH
# fixed it): when the send button specifically cannot be found, the
# driver reloads the page once, re-pastes the prompt (reload always
# loses the composer's unsent text) and retries the send lookup exactly
# once before giving up. Never triggered by any OTHER selector miss
# (prompt box, busy signal, response image, ...) — only the send button.
SEND_RELOAD_RECOVERY = True


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
    # substrings marking ChatGPT's OWN "image generation failed" answer
    # (owner 2026-07-21, BUG 3): distinct from refusal/quota — the busy
    # signal never clears for this state, so `await_done`'s "still
    # generating" loop scans for these on EVERY poll and raises
    # `ImageGenFailed` immediately instead of burning the whole
    # `generation_timeout_s` waiting for a done edge that never comes.
    # EMPTY BY DEFAULT (Gemini has shown no such failure text) — the
    # check is a silent no-op wherever this tuple is empty.
    image_failed_text_markers: tuple[str, ...] = ()
    # the NATIVE "Retry" button ChatGPT renders under its "Hmm...
    # something seems to have gone wrong." error turn (owner capture
    # 2026-07-23) — the first, cheapest rung of the image-failure
    # ladder: click it before resending any text. EMPTY BY DEFAULT =
    # the site offers no such button for this state, so the ladder just
    # skips straight to the text-retry rung.
    image_error_retry_button: tuple[str, ...] = ()
    # the sidebar "New chat" control (owner captures 2026-07-18) —
    # clicked between collections/folders when the option is on
    new_chat: tuple[str, ...] = ()
    # GUI rework Phase 17 (WEBSITE FIX, HIGH RISK / owner-dependent):
    # the attach/upload control that opens this site's file picker in
    # the chat composer, and the (often hidden-by-design) <input
    # type="file"> it drives. EMPTY BY DEFAULT = WEBSITE FIX DISABLED
    # for this site — SiteDriver.submit_fix raises FixNotConfigured
    # immediately instead of guessing. DO NOT INVENT THESE SELECTORS.
    #
    # OWNER: to enable WEBSITE FIX for a site, open its chat in the
    # automation Chrome profile, inspect the "+"/attach button and the
    # file input it drives (DevTools -> Elements — same method used to
    # capture every other selector in this file), and paste them here
    # as tuples of fallback CSS selectors, e.g.:
    #   attach_button=('button[aria-label="Attach files"]',),
    #   file_input=('input[type="file"]',),
    attach_button: tuple[str, ...] = ()
    file_input: tuple[str, ...] = ()


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
        # live capture 2026-07-21 (BUG 3 — a real run lost 7 minutes to
        # this): "Image generation failed / Try again" heading, body "I
        # wasn't able to generate the image because the image
        # generation tool encountered an error. I can't retry it
        # automatically after this kind of failure. Please send the
        # same prompt again (or simply reply with 'retry'), and I'll
        # generate it on the new request." The busy/stop signal never
        # clears for this state (no done edge ever comes), so these
        # markers are scanned for DURING the "still generating" wait,
        # not just after it gives up. Distinctive substrings only —
        # never bare "retry" (would false-positive on ordinary text).
        #
        # SECOND face, live capture 2026-07-23 (a run stopped at 17/24):
        # a generic red error turn — <p>Hmm...something seems to have
        # gone wrong.</p> above "I wasn't able to generate the image due
        # to an error on my side." — with NO "reply retry" text but a
        # native Retry BUTTON (image_error_retry_button below). Same
        # stuck-busy-signal shape, so it belongs in the SAME marker set
        # and rides the SAME recovery ladder; "wasn't able to generate
        # the image" already above also covers its body line.
        image_failed_text_markers=(
            "image generation failed",
            "wasn't able to generate the image",
            "image generation tool encountered an error",
            "can't retry it automatically after this kind of failure",
            "something seems to have gone wrong",
            "error on my side",
        ),
        # the Retry button of the "something went wrong" turn (verified
        # against the live DOM by the owner 2026-07-23, UV/RETRY
        # button.png): <button data-testid="regenerate-thread-error-
        # button" ...> — clicking it regenerates in place and the whole
        # error turn disappears.
        image_error_retry_button=(
            'button[data-testid="regenerate-thread-error-button"]',
        ),
        new_chat=(
            'a[data-testid="create-new-chat-button"]',
            'a[href="/"][data-sidebar-item="true"]',
        ),
        # WEBSITE FIX (GUI rework Phase 17) — DISABLED for ChatGPT
        # until the OWNER pastes real selectors here (see SiteConfig's
        # field comment above for exactly what to capture and how).
        attach_button=(),
        file_input=(),
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
        # WEBSITE FIX (GUI rework Phase 17) — DISABLED for Gemini
        # until the OWNER pastes real selectors here (see SiteConfig's
        # field comment above for exactly what to capture and how).
        attach_button=(),
        file_input=(),
    ),
}

# When to open a fresh chat during a run (GUI dropdown / CLI flag):
# off = one long conversation per site; collection = a new chat after
# every finished collection; folder = also between folder groups
# INSIDE a collection (primary -> colored ...).
NEW_CHAT_CHOICES = ("off", "collection", "folder")
