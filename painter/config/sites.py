"""Timing, per-site DOM state selectors, and the driving loop's small
tunables. Selectors rot with every site reskin — each DOM hook below is
a tuple of fallbacks tried in order, and when none match the driver
FAILS LOUDLY (root Rule #1) instead of guessing.
"""

from dataclasses import dataclass

# ═══════════════════════════════ TIMING ═════════════════════════════════
# --- Timing ----------------------------------------------------------

@dataclass(frozen=True)
class Timing:
    """All waits and paces, in seconds."""

    # human-like hesitation between UI actions (click box -> paste,
    # paste -> send ...): a random delay drawn from this range, like
    # a person doing Ctrl+V and then Enter.
    # NOT USER-TUNABLE (owner 2026-08-07) — see PACE section below.
    # Widened from 0.2-0.6 when the GUI spinners were removed: a narrow
    # range is a MORE regular rhythm, and regularity is what a bot
    # detector reads. The whole cost is 3-4 draws per image, about a
    # second against a ~60 s generation, so the wider spread is free.
    action_delay_min_s: float = 0.3
    action_delay_max_s: float = 0.9
    # a required element (prompt box, send button) must appear;
    # SPAs morph elements a beat after input events, so lookups
    # poll instead of failing on a one-shot snapshot
    selector_timeout_s: float = 10.0
    # submit clicked -> the busy signal (stop button) must appear
    busy_appear_timeout_s: float = 30.0
    # no busy signal after this long -> click send / press Enter again
    # (the send button is sometimes momentarily blocked)
    send_retry_after_s: float = 5.0
    # F1 protocol (owner 2026-07-29): a busy signal STILL PRESENT from
    # the previous item blocks a new send — wait this long for it to
    # clear, then page-REFRESH (never send over a busy composer)
    busy_clear_grace_s: float = 6.0
    # LIVE-RUN FIX (owner 2026-08-04): the pre-send busy wait's OWN
    # budget. It used to borrow generation_timeout_s (420s), so a stuck
    # ChatGPT stop button cost a real run 7 SILENT minutes between two
    # items. A previous generation that is honestly still running
    # finishes well inside this; anything longer is a stuck button and
    # earns a page refresh. (A button already known stuck — busy still
    # set when OUR image loaded — skips the wait entirely.)
    busy_stuck_timeout_s: float = 90.0
    # F1 protocol: after the send click, "SENT" must be CONFIRMED
    # (composer emptied + our text visible as the new user turn)
    # within this window; at half of it the send is retried once
    send_confirm_timeout_s: float = 20.0
    # F4g (owner 2026-07-29): Chrome is opened automatically at agent
    # Start; when the site shows a LOGIN page instead of the composer,
    # the run WAITS this long for the owner to log in (polling for the
    # composer, status logged) before failing loudly
    login_wait_timeout_s: float = 900.0
    # LIVE-RUN HOTFIX (owner 2026-07-29): ChatGPT's busy signal
    # FLICKERS between its text phase and its image-tool phase — a
    # "text + not busy" observation is terminal only after it holds
    # CONTINUOUSLY this long (else the item was being skipped, and the
    # next submit's refresh KILLED the still-running generation — the
    # send/interrupt/send loop the owner caught live)
    text_settle_s: float = 6.0
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
    # included (e.g. 12.56s) — less robotic pacing. The DEFAULT is the
    # POLITE pace; a run overrides the pair from PACE_RANGES via the
    # GUI's "Polite pace" switch (see below).
    pause_min_s: float = 12.0
    pause_max_s: float = 36.0


# ═════════════════════════════ THE PACE ═════════════════════════════════
# --- The two paces (owner 2026-08-07) --------------------------------
#
# The owner USED to type four numbers per site in the GUI — pause
# from/to and action-delay from/to. Those are protocol MECHANICS, not a
# product choice, and they were the only fields in the app exposing
# them, so they moved here and the GUI kept ONE switch: "Polite pace".
#
# The two ranges are not a speed dial; they are two PEOPLE (the owner's
# own model, and the reason they are allowed to OVERLAP):
#
#   POLITE  12-36 s  — someone running this alongside other work, coming
#                      back to the tab every half minute or so
#   FAST     2-13 s  — someone sitting on it, focused, next prompt as
#                      soon as the last image lands
#
# Neither is zero, and that is deliberate. Driving the consumer web UI
# breaches both sites' automation clauses (README -> Honesty Notes); the
# realistic consequence is account-level (captcha walls, rate limits,
# suspension), and the gap between requests is the largest part of what
# has kept the owner's runs unremarkable. A perfectly regular zero-gap
# cadence is the single most recognisable pattern there is, so the FAST
# pace still breathes.
#
# The site sees pause + GENERATION (~60 s), not the pause alone, so the
# real request cadence is ~72-96 s polite vs ~62-73 s fast — the daily
# image quota bites long before either becomes a rate problem.
PACE_POLITE_S = (12.0, 36.0)
PACE_FAST_S = (2.0, 13.0)


def pace_range(polite: bool) -> tuple[float, float]:
    """The (min, max) pause between images for the GUI switch's state.

    THE one authority — `gui.app_jobs` reads it for both the site runs
    and the API job, so the two can never drift apart."""
    return PACE_POLITE_S if polite else PACE_FAST_S


# The GUI switch's own default: ON. A fresh install is polite until the
# owner says otherwise.
PACE_POLITE_DEFAULT = True


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


# ═══════════════ REFUSAL SCENARIO CATEGORIES ════════════════════════════
# --- Refusal scenario categories (owner 2026-07-23) ------------------
#
# A refusal is CLASSIFIED into a scenario so the runner can pick the
# right safer-retry preamble (RETRY_PREAMBLES in config.ai): a
# violence/unsafe block and a copyright "third-party content" block need
# opposite reframings. These strings are the keys of both
# SiteConfig.refusal_markers and RETRY_PREAMBLES — keep the two in sync.
REFUSAL_SAFETY = "safety"
REFUSAL_COPYRIGHT = "copyright"


# ═══════════════ SITE CONFIG — DOM HOOK SCHEMA ══════════════════════════
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
    # substrings marking a refusal of ONE prompt — the item is reported
    # and skipped (or safer-retried), the run continues (owner
    # 2026-07-17). Keyed BY SCENARIO (REFUSAL_SAFETY / REFUSAL_COPYRIGHT,
    # owner 2026-07-23) so the runner picks the matching retry preamble.
    # The driver checks categories IN INSERTION ORDER, MOST SPECIFIC
    # FIRST: the copyright message ("may violate our guardrails ...
    # similarity to third-party content ... retry or edit your prompt")
    # also contains generic safety substrings, so copyright must be
    # listed and matched before safety or it would misclassify.
    refusal_markers: dict[str, tuple[str, ...]]
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
    # one USER turn — the F1 protocol (owner 2026-07-29) confirms a
    # send by seeing OUR text appear as the newest user turn. EMPTY =
    # confirmation falls back to "composer emptied + busy appeared",
    # loudly logged (never silent). NOTE: the ChatGPT selectors are
    # from the same data-turn / data-message-author-role family the
    # owner captured live for assistant turns (UV/ screenshots);
    # Gemini's <user-query> is the standard element — both still await
    # one live-run confirmation (they fail LOUDLY, never misbehave,
    # if wrong).
    user_turn: tuple[str, ...] = ()
    # F2 (owner 2026-07-29): the site's MODEL-DEGRADATION banner —
    # Gemini's "Limit reached. Continuing with Flash-Lite." card. Its
    # presence with NO image is ModelDegraded, not a plain quota stop:
    # the user chooses (ask / continue on the degraded model / wait
    # for reset). EMPTY = the site has no such state.
    degrade_banner: tuple[str, ...] = ()
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
    # Attaching an image into the composer (owner captures 2026-07-23,
    # UV/Add Photo/) — used by BOTH input-image sheet entries (the
    # "← `ref`" reference photo) and WEBSITE FIX (re-attaching a flagged
    # output). SiteDriver.submit_with_image acts like a PERSON: expand
    # the composer's "+" menu, THEN pick the add-image option (never a
    # hidden upload item directly).
    #
    # attach_menu_path — the ORDERED clicks to reach the file picker,
    # each a fallback tuple: [ the "+" button, the add-image menu item,
    # ... ]. The LAST click reveals the file input / opens the OS dialog.
    # EMPTY = image attach DISABLED for this site (submit_with_image
    # raises AttachNotConfigured, never guesses). DO NOT INVENT THESE.
    attach_menu_path: tuple[tuple[str, ...], ...] = ()
    # the hidden <input type="file"> the menu drives. SET -> the driver
    # calls set_input_files on it directly (no native dialog, robust —
    # ChatGPT exposes #upload-photos). EMPTY -> the LAST attach_menu_path
    # click is wrapped in Playwright's file-chooser interception instead
    # (Gemini opens an OS dialog with no input we can target).
    file_input: tuple[str, ...] = ()
    # the attached-image PREVIEW/thumbnail that appears in the composer
    # once the upload FINISHES — the driver waits for it (up to the
    # image-ready timeout) before sending, so the prompt never goes out
    # ahead of the image. EMPTY = no wait (human-rhythm hesitation only).
    attach_preview: tuple[str, ...] = ()


# ═══════════════ SITES — PER-SITE DOM CONFIG + NEW-CHAT POLICY ══════════
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
        # same attribute family as the captured assistant turns; the
        # data-message-author-role attribute is visible in the owner's
        # UV/RETRY button.png devtools capture (assistant variant)
        user_turn=(
            'section[data-turn="user"]',
            '[data-message-author-role="user"]',
            '[data-turn="user"]',
        ),
        result_image=(
            'div[id^="image-"] img',
            'img[alt*="Generated image" i]',
            'img[src*="/backend-api/"]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_markers={
            # COPYRIGHT first (owner 2026-07-23, the Star Wars run): live
            # capture "We're so sorry, but the image we created may
            # violate our guardrails concerning similarity to third-party
            # content. If you think we got it wrong, please retry or edit
            # your prompt." It ALSO carries the generic safety substrings
            # ("may violate", "retry or edit your prompt"), so its OWN
            # distinctive substrings must be checked before safety.
            REFUSAL_COPYRIGHT: (
                "third-party content",
                "third party content",
                "similarity to third",
                "guardrails concerning similarity",
            ),
            REFUSAL_SAFETY: (
                "can't create",
                "cannot create",
                "can't generate",
                "cannot generate",
                # live capture 2026-07-17: "We're so sorry, but the
                # prompt may violate our content policies. If you think
                # we got it wrong, please retry or edit your prompt." —
                # "content polic" catches both policy and policies
                "content polic",
                "may violate",
                "violate our",
                "retry or edit your prompt",
                "unable to create",
                "not able to create",
            ),
        },
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
            # live capture 2026-07-29 (read off the owner's running
            # tab): "You're out of image creations for now. Upgrade
            # your plan to continue, or wait for more tomorrow ..."
            "out of image creations",
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
            # live capture 2026-07-29 (the near-quota flaky state, read
            # off the owner's running tab): "I was unable to invoke the
            # image-generation tool right now." — transient; rides the
            # ladder, and when the quota is truly out the retry's own
            # answer carries the quota text -> TerminalState stops the
            # site cleanly. Was unmatched before: 30+ items burned as
            # false REFUSED while the plan limit was approaching.
            "unable to invoke the image-generation tool",
            "unable to invoke the image generation tool",
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
        # Image attach (owner captures 2026-07-23, UV/Add Photo/chatGPT,
        # incl. "hidden ADD PHOTO.png" — the full open-menu DOM): the
        # composer "+" is <button id="composer-plus-btn" data-testid=
        # "composer-plus-btn" aria-label="Add files and more">. Its menu
        # rows are <div class="group __menu-item ..." role="group"> — the
        # CLICKABLE row is div.__menu-item (it carries cursor:pointer;
        # OpenAI gives NO per-row data-testid, so the ONLY stable anchor
        # for the "Add photos & files" row is its label text scoped to
        # .__menu-item; role is "group", NOT "menuitem"). That row drives
        # the hidden <input type="file" id="upload-photos" data-testid=
        # "upload-photos-input" accept="image/*" multiple>, so the driver
        # sets files on it directly (no OS dialog) — the row click is only
        # for the human flow. Once uploaded, the composer shows the file
        # as <button aria-label="Open image: User uploaded image">
        # wrapping <img class="object-cover"> in a role="group" file-tile
        # — the preview the driver waits for before sending.
        attach_menu_path=(
            ('button[data-testid="composer-plus-btn"]', "#composer-plus-btn"),
            (
                'div.__menu-item:has-text("Add photos & files")',
                '[class*="menu-item"]:has-text("Add photos & files")',
                '[role="menuitem"]:has-text("Add photos & files")',
            ),
        ),
        file_input=(
            'input[data-testid="upload-photos-input"]',
            "#upload-photos",
            'input[type="file"][accept*="image"]',
        ),
        attach_preview=(
            'button[aria-label^="Open image" i]',
            '[role="group"] img.object-cover',
            'div[class*="file-tile"] img',
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
        # Gemini renders the sent prompt as a <user-query> element
        user_turn=(
            "user-query",
            '[class*="user-query"]',
        ),
        # live capture 2026-07-25 (UV/data/LIMIT Reach): the quota
        # banner element; its text carries the absolute reset moment
        # ("... until your limit resets on Jul 25 at 2:18 PM ...")
        degrade_banner=(
            '[data-test-id="gemini-quota-banner-lm"]',
            "gemini-quota-banner",
        ),
        result_image=(
            "generated-image img",
            "single-image img",
            "button.image-button img",
            'img[alt*="AI generated" i]',
            'img[src^="blob:"]',
            'img[src^="data:image"]',
        ),
        refusal_markers={
            # Only SAFETY captured for Gemini so far; add a
            # REFUSAL_COPYRIGHT group here if it ever blocks a prompt for
            # third-party-content resemblance the way ChatGPT does.
            REFUSAL_SAFETY: (
                "can't create",
                "cannot create",
                "can't generate",
                "cannot generate",
                "unable to generate",
                "unsafe",
                # live captures 2026-07-25 (UV/data/copyright gemini —
                # the market-scene incident: these texts matched NO
                # marker, so the continue nudge ran and an unrelated
                # image was saved; F1 root cause 2). Generic-guidelines
                # refusals sit under SAFETY until a distinctly-copyright
                # Gemini text is captured (REWORK.md, open items).
                "can't help with this particular request",
                "cannot help with this particular request",
                "may go against my guidelines",
                "go against my guidelines",
                "against my guidelines",
                # Gemini answers in the account's language — Serbian too
                "ne mogu da generi",
                "ne mogu da kreiram",
                "ne mogu da pomognem",
                "bezbednosn",
            ),
        },
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
        # Image attach (owner captures 2026-07-23, UV/Add Photo/Gemini):
        # the composer "+" is <button aria-label="Upload & tools"
        # aria-haspopup="menu"> (inside <gem-icon-button>); its menu's
        # "Upload files" row is <button data-test-id=
        # "local-images-files-uploader-button" aria-label="Upload files
        # ..." aria-haspopup="dialog"> — it opens the OS file dialog with
        # NO exposed <input> we can target, so file_input is EMPTY and
        # the driver catches the dialog via Playwright's file-chooser
        # interception. Once uploaded, the composer shows
        # <uploader-file-preview> holding <img class="gem-attachment-
        # style-img" alt="attachment" src="blob:..."> — the preview the
        # driver waits for before sending.
        attach_menu_path=(
            (
                'button[aria-label="Upload & tools"]',
                'gem-icon-button[aria-label*="Upload" i] button',
            ),
            (
                'button[data-test-id="local-images-files-uploader-button"]',
                'button[aria-label^="Upload files" i]',
                'button:has-text("Upload files")',
            ),
        ),
        file_input=(),
        attach_preview=(
            "img.gem-attachment-style-img",
            "uploader-file-preview img",
            'img[alt="attachment" i]',
        ),
    ),
}

# When to open a fresh chat during a run (GUI dropdown / CLI flag):
# off = one long conversation per site; collection = a new chat after
# every finished collection; folder = also between folder groups
# INSIDE a collection (primary -> colored ...).
NEW_CHAT_CHOICES = ("off", "collection", "folder")
