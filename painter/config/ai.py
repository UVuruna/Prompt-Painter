"""Prompt rules appended per site, styles, safer-retry/continue-nudge
copy, and the free Gemini API features (sheet generator, image checker,
API image generation, the Fixer AI) — owner 2026-07-17 through
2026-07-21.
"""

import re

from .paths import PROJECT_ROOT

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
    # GUI rework Phase 19 (API Image GEN, gemini-image via the paid
    # REST API): no extra rule YET — there is no live drift evidence
    # for this model the way there is for the Gemini WEBSITE's
    # reflections (that rule was captured from real observed drift);
    # add one here if the owner sees the same pattern from the API.
    "api_image": (),
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


# --- Per-agent STYLE clause (owner 2026-07-19) -----------------------
#
# Each AgentPanel picks a rendering STYLE; the chosen clause is appended
# at the very END of that site's prompt suffix (AFTER the background rule
# and the Gemini laws), only when it is not "None". Pure data — the owner
# can reword the text here without touching any logic. "None" (the
# default) maps to an empty clause = nothing appended. STYLE_CHOICES
# preserves the dropdown order (None first).
STYLES = {
    "None": "",
    "Realistic": (
        "STYLE: photorealistic, high-fidelity finish - crisp fine detail,"
        " smooth clean surfaces, natural even lighting; NO film grain, NO"
        " speckle or noise, NO gritty sandpaper texture, NO heavy painterly"
        " stylization."
    ),
    "Oil painting": (
        "STYLE: classical oil painting - visible confident brushwork, rich"
        " layered color, subtle canvas texture, painterly light."
    ),
    "Watercolor": (
        "STYLE: soft watercolor - translucent layered washes, gentle color"
        " bleeds, visible paper grain, delicate edges."
    ),
    "3D render": (
        "STYLE: clean 3D render - physically based materials, soft studio"
        " lighting, smooth surfaces, subtle ambient occlusion, crisp"
        " reflections."
    ),
    "Flat vector": (
        "STYLE: flat vector illustration - bold clean shapes, solid fills,"
        " crisp edges, minimal or no gradients, no texture."
    ),
    "Ink engraving": (
        "STYLE: fine antique engraving - precise cross-hatched linework,"
        " high-contrast ink, old-print character."
    ),
}
STYLE_CHOICES = tuple(STYLES)  # dropdown order — "None" first
STYLE_DEFAULT = "None"


def prompt_suffix(
    site_key: str,
    background: str,
    prompt_text: str = "",
    style: str | None = None,
) -> str:
    """The rule block appended to one prompt of one site.

    ``style`` (a STYLES key, "None"/None = no style) appends that style's
    clause at the very END, after the aspect/background/site rules.
    """
    rules = [_aspect_rule(prompt_text)]
    bg_rule = _BACKGROUND_RULE[background]
    if bg_rule:
        rules.append(bg_rule)
    rules.extend(SITE_PROMPT_RULES[site_key])
    if len(rules) == 1:
        suffix = f"\n\nIMPORTANT: {rules[0]}."
    else:
        numbered = " ".join(
            f"{n}) {rule}." for n, rule in enumerate(rules, start=1)
        )
        suffix = f"\n\nIMPORTANT — follow ALL rules strictly: {numbered}"
    clause = STYLES.get(style) if style else None
    if clause:  # "None" -> "" -> falsy -> nothing appended
        suffix += f" {clause}"
    return suffix


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


# --- Continue nudge (opt-in, ON by default, owner 2026-07-20) --------

# ChatGPT sometimes STALLS mid-image: the done edge fires (stop button
# gone) yet no image loads and the answer text is EMPTY — a NoImage /
# unknown-DOM state that matches no refusal/quota marker. The owner's
# fix is a plain "continue" nudge in the SAME chat, which usually makes
# it finish the pending image. On a NoImage the runner sends this ONCE
# (the prompt is already in the chat — we only tell it to continue),
# then either uses the recovered image or gives up loudly. Data only —
# the owner can reword it here.
CONTINUE_NUDGE = "Continue - please finish generating the image."


# --- Image-generation-failed retry (ChatGPT, owner 2026-07-21) --------

# BUG 3: ChatGPT's image tool sometimes fails outright ("Image
# generation failed" / "I wasn't able to generate the image ... reply
# with 'retry'") while the busy/stop signal never clears — the driver
# raises ImageGenFailed the instant it recognizes the site's own
# SiteConfig.image_failed_text_markers (empty for sites with no such
# marker, e.g. Gemini) instead of waiting out the whole
# generation_timeout_s. ChatGPT's own message says exactly how to
# recover: reply with this word, in the SAME chat.
IMAGE_RETRY_NUDGE = "retry"
# how many times the runner resends IMAGE_RETRY_NUDGE before giving up
# on the item (same shape as safer_retry's one-shot preamble resend,
# but this failure is flaky enough on the owner's runs to warrant more
# than one attempt)
IMAGE_FAILED_RETRY_MAX = 2


# --- AI features: free Gemini API (owner 2026-07-20) ------------------
#
# painter/ai.py drives the FREE AI Studio REST API (no SDK) for two GUI
# features: the sheet GENERATOR (text model) and the image CHECKER
# (vision model). Model names ROTATE with Google's releases — they are
# DATA here so the owner can bump them without touching code. The key
# lives in settings.json (gitignored) under GEMINI_KEY_SETTING; the GUI
# wizard writes it there and painter.ai reads it per call.
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# The stable "-latest" aliases: Google keeps them pointed at a current
# free-tier flash model, so they don't 404 ("no longer available to new
# users") or 429 (free_tier limit 0) the way the pinned 2.0/2.5 names did
# for fresh keys. Verified 200 OK against a new AI Studio key 2026-07-21.
GEMINI_TEXT_MODEL = "gemini-flash-latest"    # sheet generator (free tier)
GEMINI_VISION_MODEL = "gemini-flash-latest"  # image checker (multimodal, reads images)
# GUI rework Phase 18 (API Image Generation): the image-generation/edit
# model, separate from the free TEXT/VISION models above. PAID-ONLY on
# the owner's key TODAY — every free-tier quota for this model is 0
# (verified live against a real captured 429, 2026-07-21; see
# AI_IMAGE_QUOTA_MARKERS below and ai.PaidFeatureRequired), so a call
# raises loudly until the owner enables billing on the AI Studio
# project. Google is retiring THIS generation in October 2026 in
# favour of "Nano Banana 2" (gemini-3.1-flash-image) — bump this
# string when that lands; nothing else in the code names the model.
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
GEMINI_KEY_SETTING = "gemini_api_key"     # the settings.json key name
# where the wizard's step-1 button sends the browser (the key page)
AI_STUDIO_URL = "https://aistudio.google.com/apikey"
# free-tier pacing: the flash free tier allows ~10 requests/minute, so
# consecutive calls keep at least this many seconds apart (6.0 would sit
# exactly on the limit; 6.5 leaves headroom for clock skew)
AI_CALL_PAUSE_S = 6.5
AI_TIMEOUT_S = 120.0  # one HTTP call's hard cap (vision calls are slow)
# the wizard's "Test key" prompt — tiny and cheap, the answer is shown
AI_TEST_PROMPT = "Reply with exactly: OK"
# TRANSIENT API failures RETRY (the free tier 503s under load, 429s at
# the rate cap); PERMANENT ones (400 bad request, 401/403 bad key, 404
# no such model) raise on the first try. The client keys the retry on
# the HTTP status.
AI_TRANSIENT_STATUS = frozenset({429, 500, 503})
AI_RETRY_MAX = 3        # total attempts per call before giving up loudly
AI_RETRY_BACKOFF_S = 5.0  # fixed wait before a 503/500 retry
# a 429 carries the server's own backoff (error.details[].retryDelay /
# "please retry in Xs"); honour it, but never wait longer than this
AI_RETRY_MAX_WAIT_S = 30.0

# GUI rework Phase 18: the free-tier-EXHAUSTED signal that makes a 429
# PERMANENT (ai.PaidFeatureRequired) instead of transient. Each inner
# tuple is an AND-group — every substring in it must appear
# (case-insensitive) in the 429 message for that group to fire; the
# whole marker fires when ANY group matches (OR across groups).
# Captured VERBATIM from the owner's key against GEMINI_IMAGE_MODEL,
# 2026-07-21 (the exact body lives in ai.md / test_ai.py's fixture):
#   "You exceeded your current quota, please check your plan and
#   billing details. ... Quota exceeded for metric: ...
#   generate_content_free_tier_input_token_count, limit: 0, model:
#   ... Quota exceeded for metric: ...generate_content_free_tier_
#   requests, limit: 0, model: ... Please retry in 15.776751513s."
# TRAP (do not "fix" this): that body ALSO names a "retry in Xs" hint,
# same as an ordinary transient rate-limit 429 — classification keys
# on THESE substrings only, never the retry hint. A 429 matching
# NEITHER group is ambiguous and stays TRANSIENT (retries as today) —
# retrying a permanent error wastes a few calls, but giving up on a
# genuinely transient one is worse (owner decision).
AI_IMAGE_QUOTA_MARKERS = (
    ("free_tier", "limit: 0"),
    ("check your plan and billing details",),
)

# --- API Image Generation job (GUI rework Phase 19) --------------------
#
# The "Check API access" probe (ApiImageGenPanel) makes ONE real
# generate_image call with this tiny, cheap prompt — the only way to
# learn whether the free-tier-zero signal (PaidFeatureRequired) still
# fires is to actually call the paid endpoint, same as the key
# wizard's own AI_TEST_PROMPT probes the free text model.
AI_IMAGE_PROBE_PROMPT = (
    "A single small red circle on a plain white background, minimalist"
    " icon."
)
# the owner-facing message when the probe (or a live run) hits
# PaidFeatureRequired — gates the panel's Start button. Exact wording
# is a product decision (owner 2026-07-21), kept here like every other
# user-facing copy constant (SAFER_PREAMBLE, CONTINUE_NUDGE).
AI_IMAGE_GATE_MESSAGE = (
    "API image generation needs billing enabled — free tier limit is"
    " 0; use Website GEN for free."
)

# --- the AI sheet generator (owner's #2: follow-up questions) ---------
AI_MAX_QUESTIONS = 6  # the clarifying poll is capped at this many
# where AI-generated sheets are saved (owner content, NOT gitignored —
# but never committed by an agent either; the dir is created on demand)
SHEETS_DIR = PROJECT_ROOT / "sheets"
# FIRST call system prompt: the contract + "questions only". {contract}
# is instructions.md verbatim; {max_q} is AI_MAX_QUESTIONS.
AI_QUESTIONS_SYSTEM = (
    "You help an operator author a PromptPainter prompt-sheet (.md"
    " file). This is the sheet contract you must know:\n\n{contract}\n\n"
    "DO NOT produce the sheet yet. First return ONLY a short numbered"
    " list of clarifying questions (at most {max_q}), one question per"
    " line, no other text before or after. Ask only what the request"
    " leaves unknown of: theme and visual style, image count, the drop"
    " folder (assets/<category>/<rest>), file naming, background"
    " (transparent / white), shape (rondel / lancet / plate), any"
    " special laws."
)
# SECOND call system prompt: the contract + "the raw .md only".
AI_SHEET_SYSTEM = (
    "You author a PromptPainter prompt-sheet (.md file). Follow the"
    " sheet contract EXACTLY:\n\n{contract}\n\n"
    "Return ONLY the raw markdown of the complete sheet — no"
    " commentary, no surrounding code fence around the whole file. It"
    " must carry exactly one '# H1' theme line and, per image, a"
    " '**Title** → `assets/<category>/<rest>/<File>.png`' line followed"
    " by one fenced prompt block."
)
# SECOND call user content: the request + the answered poll.
AI_SHEET_REQUEST = (
    "The operator's request:\n{request}\n\n"
    "The operator answered the clarifying questions:\n{qa}\n\n"
    "Write the complete sheet now."
)
# ONE automatic repair round when the parser rejects the produced md.
AI_REPAIR_PROMPT = (
    "The sheet you produced fails the PromptPainter parser with these"
    " problems:\n{problems}\n\nHere is the sheet you produced:\n\n{md}"
    "\n\nReturn the corrected COMPLETE .md (raw markdown, no"
    " commentary, no code fence around the whole file), fixing every"
    " listed problem and keeping everything else identical."
)

# --- the AI image checker (owner's #3: banal defects only) ------------
AI_FLAGS_FILENAME = "ai_flags.json"  # under <out>/_state/
# the vision instruction — BANAL defects only, in a strict short format
# the parser (painter.ai.parse_check_response) can read
AI_CHECK_INSTRUCTIONS = (
    "You are a strict quality checker of AI-generated decorative images"
    " (badges, rondels, stained-glass panels, emblems, plates). Look"
    " ONLY for these BANAL defects: the subject or its circle/frame"
    " slightly CUT OFF at an image edge; leftover background patches or"
    " halos around the subject; stray lines, smudges or floating"
    " artifacts; watermark or text artifacts; an obviously clipped or"
    " asymmetric frame. IGNORE style, beauty and artistic choices —"
    " they are not defects.\n"
    "Respond in EXACTLY this format: if the image is clean, reply with"
    " the single line 'OK'. Otherwise reply with the first line"
    " 'DEFECTS:' followed by one short defect description per line,"
    " each line starting with '- '."
)
# the per-item extra suffix appended when a flagged image is re-sent to
# its original generator ({defects} = the '; '-joined defect list)
AI_FIX_NOTE = (
    "The previous attempt had these flaws: {defects}. Regenerate the"
    " same image correcting them."
)

# --- the Fixer AI (GUI rework Phase 20, owner's UV/prompt.txt item 1/2:
# "ako ustanovi gresku salje fikseru da ispravi"; "u oba slucaja kreira
# PROMPT koji salje uz sliku") -----------------------------------------
#
# gui.ai.build_fix_prompt(defects, raw) turns a checked image's defect
# list (+ its verbatim raw response, for extra context the parsed
# bullets can lose) into the instruction sent ALONGSIDE the flagged
# image to ai.edit_image (IMAGE FIX) or driver.submit_fix (WEBSITE
# FIX) — both the manual report-viewer buttons and the API-mode auto-
# fixer share this ONE function. Two templates: WITH named defects (the
# common case) and a graceful NO-defects fallback (never blank —
# edit_image/submit_fix always need SOME instruction text; a checker
# that flags an image with an empty defects list is a malformed corner
# case this function stays honest about regardless of what the caller
# already gates on).
AI_FIX_PROMPT_WITH_DEFECTS = (
    "A quality check found defects in this image. Fix ONLY these,"
    " keeping composition, colours and style exactly as they are"
    " otherwise:\n{bullets}"
)
AI_FIX_PROMPT_NO_DEFECTS = (
    "A quality check flagged this image as needing correction but"
    " named no specific defect. Use your own judgement to fix whatever"
    " looks wrong, keeping composition, colours and style exactly as"
    " they are otherwise."
)
# appended verbatim when the checker's raw response is available —
# {raw} is NOT the parsed defects list above (already folded into the
# instruction) but the model's own words, which sometimes carry
# qualifying detail ("the halo is on the LEFT side") the parsed bullets
# flatten away.
AI_FIX_PROMPT_RAW_SUFFIX = "\n\nFull quality-check report:\n{raw}"

# the Fixer AI's dispatch MODE (AgentPanel.fixer_mode_var): "api"
# (ai.edit_image, a REST call that runs on a background thread
# genuinely IN PARALLEL with the site's own next-image generation — the
# intended flow) or "website" (driver.submit_fix — QUEUED instead of
# driven immediately, since the site's browser tab is busy generating
# the NEXT image the instant a checker result lands; see
# gui.PainterGui._queue_website_fix's own docstring for exactly why).
# The value strings double as the AgentPanel dropdown's own display
# text (Rule #4, same convention as NEW_CHAT_CHOICES/ASPECT_FILTER_MODES
# above).
FIXER_MODE_API = "api"
FIXER_MODE_WEBSITE = "website"
FIXER_MODE_CHOICES = (FIXER_MODE_API, FIXER_MODE_WEBSITE)

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
