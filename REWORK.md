# BIG REWORK — Binding Plan (owner Q&A, 2026-07-29)

**Status: BINDING.** This plan was settled in a dedicated brainstorm
session: the owner's brief (`UV/prompt.txt`), a full code-flow audit,
a written question list, and the owner's per-item answers (written
back into `UV/prompt.txt`, 2026-07-29). Where this file conflicts
with [CLAUDE.md](CLAUDE.md) sections written earlier, THIS FILE WINS
until each phase lands and folds its outcome back into CLAUDE.md and
the module `.md` docs (Rule #3).

Every phase is ONE focused future session. A session takes its phase
spec below, implements it INLINE (Rule #15: no workflows, no agent
fleets — agents only for genuinely independent parallel pieces),
pins the fixed bugs with regression tests named after the failure
(Rule #25), updates the docs, commits per the version convention,
and builds+releases (Rule #24).

## Table of Contents

- [Root causes this rework kills](#root-causes)
- [Phase F1 — Core submit/await/extract protocol](#f1)
- [Phase F2 — Failure ladder, cooldown memory, Flash-Lite choice](#f2)
- [Phase F3 — Run lifecycle and dashboard continuity](#f3)
- [Phase F4 — UI rework](#f4)
- [Phase F5 — API model discovery + image attach](#f5)
- [Phase F6 — Checker rework (prompt-aware)](#f6)
- [Phase F7 — Prompt helpers](#f7)
- [Open items](#open-items)

<a id="root-causes"></a>

## Root causes this rework kills (audit 2026-07-29, all verified)

1. **Duplicate image saved under a new name ("AI 1s" rows).**
   `extract_image` takes the LAST visible image on the page with no
   link to OUR submit; combined with a STUCK busy button (ChatGPT
   keeps the stop state from the previous item), `await_done`
   mistakes the stale busy signal for our generation and then grabs
   the previous item's image.
2. **Unrecognized Gemini refusal → continue nudge → unrelated image
   saved.** Gemini's "I'm sorry, it appears I can't help with this
   particular request" / "may go against my guidelines" are NOT in
   `refusal_markers` (`painter/config/sites.py`), so the NoImage
   branch sends the continue nudge and Gemini draws something random
   (the market-scene case) — which gets saved under the item's name.
3. **A refusal surfacing INSIDE the image-failed recovery ladder
   stops the whole site** instead of skipping the item: the ladder
   runs inside the `except ImageGenFailed` handler, so the sibling
   `except ItemRefused` never catches it (`painter/runner.py`,
   confirmed by the owner's Star Wars run log).
4. **"Image is there but the tool doesn't take it."** A text turn
   arriving AFTER the image turn makes the "last response container"
   image-less → NoImage. Done-edge is button-only, so a stuck stop
   button also stalls the wait long after the image is visible.
5. **Start wipes the dashboard.** `DashPanel.reset()` runs on EVERY
   Start — including the automatic quota restart — so a mid-batch
   stop costs the whole visual history.
6. **Quota cooldown forgotten on app close.** The restart deadline
   lives only in an in-memory Tk timer; nothing is persisted.
7. **Resume-after-stop re-runs finished ticked items as `_vN`
   redos.** A selection is static: items completed in the interrupted
   run are still ticked on restart, and "ticked + on disk" currently
   means deliberate redo.

<a id="f1"></a>

## Phase F1 — Core submit/await/extract protocol (turn-based)

**Kills root causes 1–4. The most critical phase; do it first.**
Files: `painter/driver.py`, `painter/config/sites.py`,
`painter/runner.py`, tests.

The driver stops trusting the busy button as the only truth and
instead tracks FOUR element states per site tab (owner's decree,
`UV/prompt.txt` §1A):

1. **TEXTAREA** — empty / holds our prompt / holds something else
   (if empty, skip the select-all + delete).
2. **SEND–BUSY button** — ready / busy / absent: is the site free
   for a new prompt, processing, or wedged.
3. **PREV TEXT SENT** — the last USER turn's text: is the site
   working on THE prompt we queued, not a leftover.
4. **PREV IMAGE** — the last assistant turn's image state: finished
   (downloadable) or still rendering.

### The protocol (pseudocode — language-neutral, Rule #21)

```
BEFORE SEND:
    baseline.turn_count = count(assistant turns)
    baseline.last_img   = src/hash of last generated image (or none)
    IF button == BUSY:
        wait a short grace period for it to clear
        IF still BUSY -> page REFRESH        # never send over a busy composer
TYPE:
    IF composer not empty -> select-all + delete
    insert prompt
    VERIFY composer text starts with our prompt -> retype once, else loud fail
SEND:
    click send
    VERIFY (within a confirm timeout):
        composer is EMPTY
        AND a NEW user turn exists containing our prompt text
    -> only then state = SENT                 # never assume
    on verify failure: one send retry, then loud fail
AWAIT (poll until generation timeout):
    new_turn = assistant turn with index > baseline.turn_count
    IF new_turn holds a LOADED image (>= MIN_IMAGE_PX,
       src != baseline.last_img)             -> DONE (image wins;
                                                button is secondary)
    IF new_turn text matches quota / refusal / image-failed markers
                                             -> classify and raise
    IF new_turn has final text, NO image, and button is READY again
                                             -> UnknownNoImage:
                                                LOUD SKIP of the item
                                                (report + Check column)
EXTRACT:
    bytes ONLY from that new turn's image
    IF src/hash == previously saved image    -> DuplicateImage error
                                                (treated as not-sent)
```

**Nudge policy (owner A2):** the continue nudge is sent ONLY when
the new turn is truly empty/interrupted (no text, no image) or no
new turn ever appeared — NEVER after a text answer. An unmatched
refusal-like text is a loud per-item skip, never a nudge.

**Marker additions:** Gemini gains the generic-guidelines refusal
markers ("can't help with this particular request", "may go against
my guidelines", Serbian variants) — classified under SAFETY for now
(the safer preamble applies); a Gemini copyright group is added the
day a distinctly-copyright Gemini message is captured.

**Ladder leak fix (root cause 3):** an `ItemRefused` raised anywhere
inside the recovery ladder is handled exactly like a first-attempt
refusal — safer retry once (per category), then per-item skip. The
site stops only for quota/exhausted-ladder.

**Testability:** the decisions (classify response text, accept/reject
a candidate image, verify-sent logic) become PURE functions driven by
a snapshot of the four element states, unit-tested against fixtures
replaying each captured failure: stuck-button, duplicate-src,
market-scene nudge, refusal-inside-ladder, text-after-image. The DOM
I/O layer stays thin.

<a id="f2"></a>

## Phase F2 — Failure ladder retiming, cooldown memory, Flash-Lite

Files: `painter/config/ai.py`, `painter/config/sites.py`,
`painter/runner.py`, `gui/app_jobs.py`, `painter/settings.py`.

- **Ladder (owner A3):** rung 1 = native Retry button (unchanged);
  rung 2 = "retry" text ×3, each after a RANDOM 3–6 min wait;
  rung 3 = escalation ×3 (refresh → new session → full prompt), each
  after a RANDOM 12–15 min wait. Worst case ≈ 60 min, then the site
  stops. Randomness stays everywhere.
- **Cooldown memory (owner B1/B2):** when a quota reset time is
  parsed, persist `{site: reset_epoch}` (settings.json). On app
  start, an active cooldown produces a WARNING plus a visible
  countdown; during setup the info sits next to the site's icon.
  A cooldown NEVER blocks Start — it is information only.
- **Flash-Lite degradation (owner B3):** the Gemini quota banner
  (`data-test-id="gemini-quota-banner-lm"`; title + description carry
  the reset time) is detected as MODEL DEGRADATION, not a plain stop.
  A setting `on_model_degrade` = `ask` (default, popup) /
  `continue` (keep generating on the degraded model) / `wait` (treat
  as quota stop with auto-restart at the parsed reset time).

<a id="f3"></a>

## Phase F3 — Run lifecycle and dashboard continuity

Files: `gui/app_jobs.py`, `gui/dash_panels.py`,
`gui/select_window.py`, `gui/app_settings.py`.

- **Start never wipes (owner C1):** `DashPanel.reset()` leaves the
  collections tree and both stat scopes ALONE; a new run appends into
  the existing tree and continues the counters. Clearing is ONLY an
  explicit "Clear" button on the panel.
- **Quota auto-restart (owner C2):** continues seamlessly — no reset
  of any kind.
- **No cross-app persistence (owner C3):** a fresh app launch is a
  fresh setup; the dashboard is in-memory only.
- **Selection lifecycle (owner C4 — the `_vN` landmine):** the
  selection is LIVE, not a snapshot: every `item_done` removes the
  item from the pending selection, so a restart re-submits only the
  remainder. Redo-versioning happens ONLY for items the owner
  explicitly ticked while they were shown GREEN (done) in the Select
  window — the selection records that `redo` flag per item at tick
  time. On resume, "on disk but not flagged redo" = SKIP, never a
  version. Regression test: interrupt mid-selection, restart, assert
  zero `_v2` files.

<a id="f4"></a>

## Phase F4 — UI rework

Files: `gui/` (menu, app_build, app_views, agent_panel, tool_panels,
dash_panels, tool_dash, viewers, select_window), `painter/config/`
(jobs, theme). Follows [DESIGN.md](../../DESIGN.md) (Rule #16).
The largest phase — may be split into two sessions (4a–4d screens,
4e–4h dashboard/viewer) if the first session says so in writing.

- **4a HOME screen (owner G1):** the landing grid keeps its card
  system; every card = logo + title + a short ABOUT paragraph.
- **4b Setup screen (owner G2):** LEFT = the feature's settings; an
  option owning fine-tune settings opens a NESTED sub-panel below
  and to the right of it (collapse/expand; activating the option
  auto-expands it once). RIGHT = the drop zone for input files /
  folder — TWO sections when the feature needs both an `.md` sheet
  source and images. TOP = one thin icon-only strip: HOME leftmost,
  feature icons centered, then (right side, in order) the
  grid/slider dashboard toggle and LAST at the edge the day/night
  switcher.
- **4c Website GEN = ONE panel (owner G2/G3):** site checkboxes
  (ChatGPT / Gemini) replace the two parallel `AgentPanel`s. Both
  ticked = ONE set of settings applies to both and one Start runs
  both. One ticked = the settings apply to that site only; another
  Website GEN instance can be opened later for the other site.
  Instances are fully independent: their own sheets, their own
  output folders, even the same sheet into different folders.
- **4d Select images (owner G4):** reachable ONLY from the setup
  screen; shows ONLY the ticked sites' columns. Collection/folder
  rows get traffic-light squares: GREEN all done, YELLOW partial,
  RED nothing done. Leaf-row coloring keeps today's rules.
- **4e Dashboard grid + slider (owner G5):** the per-count column
  table is DELETED; all cards are treated identically and laid out
  purely by window width against a configured card MIN WIDTH
  (1×N narrow … 4×2 full screen). Second display mode: SLIDER —
  exactly one card at full width with ←/→ arrows. The mode toggle
  lives in the top strip (see 4b).
- **4f Image viewer rework (owner G6/G7):** opens PORTRAIT, sized so
  no button is ever cut off. Row 1 = buttons; row 2 = TITLE = the
  image NAME (never the full drop path). NEXT/PREV walks the same
  collection/folder in ONE window (done images; refused entries are
  listed but shown as their refusal reason). Below the prompt text,
  two EXPANDABLE sub-sections (styled as sub-titles, not top
  buttons): **Check** — the AI checker's report, present only when
  the checker ran for this run; **Steps** — thumbnails of the kept
  pipeline steps, present only when steps exist; clicking a
  thumbnail swaps it into the main view, with a "Restore to this
  step" action. Top-right always: **Delete** — deletes exactly the
  DISPLAYED version file from disk (confirm dialog; the row/tree
  updates; the item becomes pending again); in tool jobs
  (BG/Crop/Upscale/Aspect) the same slot is **Restore** instead.
- **4g Chrome becomes automatic (owner G8):** the "Open Chrome
  (login)" button is REMOVED. Starting an agent ensures Chrome
  itself: if a usable logged-in site tab exists → attach and go; if
  Chrome/tab must be opened → open it and, when the site shows a
  login page, WAIT (poll for the composer element, long timeout,
  status line "waiting for login…") until the owner logs in, then
  proceed. No separate manual step exists.
- **4h Folder double-click long view (owner H1):** the
  one-long-document view of a whole folder/collection is the crash
  suspect (possibly just too large). Render it INCREMENTALLY (lazy
  images, chunked build), and wrap it in top-level error logging so
  any recurrence pins itself in `logs/` (Rule #25 — the bug is not
  declared fixed; it is instrumented and mitigated until it can be
  reproduced).

<a id="f5"></a>

## Phase F5 — API model discovery + image attach

Files: `painter/ai.py`, `painter/config/ai.py`, `gui/api_panel.py`.

- **Model discovery (owner D1/D2):** call the ListModels endpoint
  with the owner's key; filter by capability; offer the models per
  PURPOSE (image generation / vision check / text generation) in the
  UI. Default = the recommended model per purpose from a maintained
  ranking table in config (best-for-the-job, not one-size-fits-all);
  when the table does not know the fetched models, recommend the
  newest. The hardcoded model constants become fallbacks only.
- **Image attach over the API (owner D3):** `generate_image` gains an
  optional input image (the `inlineData` payload `edit_image` already
  builds), and `ApiImageAdapter` gains `submit_with_image` — closing
  the audited gap where a sheet item with `← ref` run through the API
  job would call a method that does not exist.

<a id="f6"></a>

## Phase F6 — Checker rework (prompt-aware)

Files: `painter/ai.py`, `painter/config/ai.py`,
`gui/app_checker_fixer.py`, `gui/tool_panels.py`, `gui/app_tools.py`.

- **Parallel checker (owner E1):** DEFAULT = quality checks + PROMPT
  MATCH — the request now carries the image AND the item's sheet
  prompt, and asks additionally "does the image show what the prompt
  describes?" (the tilted-cosmos case). The AI-check toggle gets a
  fine-tune sub-panel (4b pattern) where the owner can drop to
  quality-only.
- **Standalone checker (owner E2):** TWO inputs — `.md` file/folder
  AND image file/folder. The tool pairs them by the sheet's drop
  path (via `drop_and_site_for`); a check runs ONLY where an image
  physically matches a sheet location — whole prompts folder + one
  image = exactly one prompt-aware check. Images supplied WITHOUT any
  `.md` input keep today's behavior: default quality checks only.
- **Flag flow (owner E3):** unchanged — a "wrong content" flag lands
  in `ai_flags.json`, the Check column, and offers the same IMAGE
  FIX / WEBSITE FIX / re-generate paths as any other defect.

<a id="f7"></a>

## Phase F7 — Prompt helpers

Files: `painter/config/ai.py`, `gui/agent_panel.py` (or its 4c
successor), docs.

- Per-agent (ChatGPT / Gemini / API) toggles, each ON/OFF:
  **no mirror** (Gemini reflections law generalized), **no empty
  space** (anti-aspect-waste: the subject fills the canvas; a round/
  square subject yields a square image with the subject near the
  frame edges — final wording owner-approved before landing),
  **no grainy / no oversharpen** (the ChatGPT anti-grain law
  generalized).
- **Background dropdown (owner F1):** `DEFAULT` (per-site: ChatGPT
  transparent, Gemini white — the value used when one setup drives
  both sites) / `TRANSPARENT` / `WHITE` / `BLACK` / `CUSTOM` with a
  color wheel.
- Helper TEXTS are drafted by the session and approved by the owner
  BEFORE landing (owner F2).
- Block-helpers (refusal preambles per category, quota markers,
  site-problem ladder) stay as F1/F2 shaped them; this phase only
  fills marker gaps found along the way.

<a id="open-items"></a>

## Open items

- **H1 crash** (double-click on a dashboard folder → long view):
  not reproducible on demand; mitigated + instrumented in 4h. NOT
  declared fixed (Rule #25) until a run reproduces or a month of
  runs stays clean.
- **Gemini copyright category:** generic-guidelines refusals are
  classified SAFETY until a distinctly-copyright Gemini text is
  captured live; then a `REFUSAL_COPYRIGHT` marker group is added.
- **F4 split decision:** the F4 session states in writing whether it
  ships whole or splits into 4a–4d / 4e–4h.
