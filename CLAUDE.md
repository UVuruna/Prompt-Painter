# CLAUDE.md — PromptPainter

Project-specific guidance for Claude Code. **Inherits ALL rules from
the monorepo root [CLAUDE.md](../../CLAUDE.md)** (the constitution) —
read that first, then use its Router table to load only the rulebook
your job needs (`../../rules/`). This file states ONLY what is
specific to PromptPainter — decisions, workflow, DOM states — and
never restates a root rule. Language follows root
[CLAUDE.md](../../CLAUDE.md) → Universal Conduct (Serbian/Latin with
the owner, English in all files) — no project-specific tightening.

**Enforcement (installed 2026-08-01, layout teeth added since):** six
guard tests run via `tests/run_guards.py`, wired into
`.claude/settings.json` (PostToolUse fast pass + Stop full pass) — see
[Code Rules](../../rules/CODE.md) → Enforcement for the spec this
project follows.

- **Fast pass** (every Edit/Write): `tests/test_structure_law.py`,
  `tests/test_config_sections.py`, `tests/test_layout_law.py` (the
  static half of THE SPACE & LEGIBILITY LAW — a banned-API grep, costs
  nothing).
- **Full pass** (Stop, session end): the three above plus
  `tests/test_docs_coverage.py`, `tests/test_doc_links.py`, and
  `tests/test_layout_audit_tk.py` (the runtime half — builds the real
  Tk window off-screen at its declared minimum and measures it).

GUI work here is ALSO governed by Zubi v2 — Algorithmic Teeth & Grader
v2 ([GUI Rules](../../rules/GUI.md#zubi-v2)). Status: **FIRST Tk
ROLLOUT (2026-08-11, owner's order)** — this project authored the Tk
template (`tests/layout_checks_tk.py`, copied to
`rules/templates/layout_checks_tk.py` for the next Tk project):
ALG-5 uniform siblings, ALG-6 radius tiers (judged on the RENDERED
radius — CTk clamps to half the shorter side), ALG-7 empty band (the
measured form of BUG A), run by `tests/test_layout_zubi_tk.py` over
the whole window registry PLUS the long-refusal ImageViewer fixture,
with a planted-violation self-test; wired into the Stop full guard
pass. Documented gaps (grader checklist, as in the Qt template):
ALG-2 contrast, ALG-3 hover, ALG-8 live profile, ALG-9 taxonomy.

---

## What This Project Is

A supervised automation tool that GENERATES IMAGES from the owner's
prompt-sheet `.md` files by driving his ALREADY OPEN, already
logged-in Gemini/ChatGPT browser tab: paste a prompt, wait for the
generation to finish, capture the image, save it under the sheet's
own filename into the theme's folder. The sheets live in his other
projects (first consumer: Watch Academy `research/prompts/`); this tool
only consumes them.

The full design discussion lives in [PLAN.md](PLAN.md) — this file
is the binding spec. **A BIG REWORK is planned (owner Q&A
2026-07-29): [REWORK.md](REWORK.md) is BINDING and wins over any
conflicting section below until each phase lands and is folded back
in here.**

## Decisions Already Made (owner 2026-07-16 — do not relitigate)

- **Name:** PromptPainter. **Stack:** Python + `playwright`.
- **Mechanic:** ★ CDP ATTACH — Chrome runs with
  `--remote-debugging-port=9222`; the tool attaches with
  `playwright.chromium.connect_over_cdp` and drives the DOM. NO
  browser extension, NO OCR, NO virtual mice (extension = plan B if
  a site blocks CDP; MouseMux = plan C of last resort).
- **No Download clicks:** when the response `<img>` appears, read
  the image BYTES from the DOM inside `page.evaluate` —
  CANVAS-FIRST (`drawImage` + `toDataURL`, since Gemini's CSP
  blocks `fetch()` of `blob:` srcs; always yields real PNG),
  `fetch()` as fallback — and save the file DIRECTLY under the
  sheet's filename; there is no rename/move step.
- **Supervised runs:** the owner watches the windows, at least
  until the tool has proven itself; paced (configurable pause
  between prompts).

## The Workflow (owner 2026-07-17 — supersedes where it differs)

1. The owner starts the app with **`python main.py`** — no
   arguments opens the GUI (the usual front door); sheet arguments
   run the single-site CLI instead.
2. He queues **ONE OR MORE sheet `.md` files** and picks the OUTPUT
   folder. Each site works through the queue IN ORDER, closing
   sheet after sheet — a quota stop mid-batch never costs finished
   work (per-sheet progress + report live beside the images), and
   the next Start resumes the rest. The goal: queue 15 sheets,
   go ride a bike. **"Select images..."** opens the tick list —
   PER SITE (ChatGPT and Gemini each get their own selection);
   already-done items show green and RE-TICKABLE — ticking one
   REDOES it as the next `_vN` version file (owner 2026-07-27, see
   The Run Loop). Beside it sits the **"Prompt + Image"** toggle
   (faza 2, owner 2026-08-03): ON reveals the reference-run section
   (Reference folder + live per-entry eligibility view) and narrows
   the run to complete prompt+reference pairs — see 3b. The
   functionality's name is **Website Image GEN** (renamed from
   Website GEN, owner 2026-08-03). **"BG removal only..."**
   runs the background remover standalone, in place, over any
   existing folder of images.
3. He picks the sites: **Gemini, ChatGPT, or BOTH IN PARALLEL** —
   one window and one thread per site, each at its own pace (still
   ONE window PER SITE, never parallel hammering of the same site).
4. The tool opens the automation Chrome itself (button / pre-run
   check). **Chrome 136+ refuses CDP on the default user profile**,
   so it launches with the project's own profile folder
   (`chrome-profile/`, gitignored) — the owner logs in there ONCE;
   sessions persist across runs.
5. Every prompt gets the site's **rule suffix** appended. The GUI
   has a background dropdown PER SITE (`transparent` / `white` /
   `none`), preselected to the site's default — ChatGPT
   transparent, Gemini white. **Gemini additionally gets the
   NO-reflections law in EVERY prompt** (2026-07-17, after the
   rondel_Dawn/rondel_Shield drift). **ChatGPT gets the ANTI-GRAIN
   law in EVERY prompt** (owner 2026-07-27, the Voljin_gpt case:
   glow words + "photorealistic" render as clouds of bright
   speckles that dissolve the subject into noise — no film grain,
   glow soft and contained, subject separated; sheet authors also
   cap glow per instructions.md rule 3b). The old ASPECT RATIO law —
   inferred from prompt keywords (TALL/lancet → portrait, else
   1:1) — was REMOVED (owner 2026-07-22, after "a tall
   lotus-tipped sceptre" flipped a ROUND medallion to portrait):
   the tool NEVER infers the aspect from the text; the sheet
   author states it explicitly in every prompt
   (instructions.md rule 3b lists what a prompt must declare —
   aspect ratio, shape/framing, unusual background).
6. After every save, the **postprocess hook** runs — THREE
   composable steps (owner's #7, 2026-07-18), each toggleable per
   run, all defaulting ON: `remove_background`
   (`painter/postprocess.py` over the IN-HOUSE
   `painter/bg_remove.py` internals — moved from Watch Academy tools,
   owner 2026-07-17: no part of this program lives in another
   project; ONE colour-keyed engine clears the border-connected
   region around a target colour, and its MODE (owner 2026-07-28)
   is AUTO-detect per file (already-transparent nothing; white or
   black cleared; else the colour the FOUR CORNERS agree on, logged;
   only disagreeing corners are reported and left untouched), a
   FORCED white/black, or a CUSTOM COLOUR ± X % per channel (0 % =
   exactly that hex) that clears ANY background colour — the
   standalone BG tool's own always-visible dropdown, with a themed
   colour picker on the swatch, the three per-path safety guards as
   its Advanced fine-tune in PERCENT, and a REACH choice: the removal
   is a FLOOD FILL from the frame by default, so a same-coloured
   region ENCLOSED by the subject (the counters inside letters) stays,
   while "everywhere" clears every matching pixel),
   `crop_transparent` (autocrop to the content box + a small config
   margin), and `upscale_if_small` (`painter/upscale.py`,
   Real-ESRGAN ncnn-vulkan binary auto-downloaded into `tools/`,
   gitignored) — ONLY images with aspect W/H in 0.9–1.1 AND a
   dimension under 800 px, upscaled native-4x then LANCZOS so no
   dimension stays below 800. Failures are loud but never kill the
   run.
7. **THE PATH IN THE SHEET IS THE PATH** (owner decree 2026-08-14 —
   binding, supersedes the "assets mirror" wording of 2026-07-18/22).
   The sheet is written BY the project that wants the image and
   states exactly where that image belongs. PromptPainter does not
   read a root out of it, does not strip a segment, does not add a
   folder of its own, and NEVER decides another project's structure.
   It appends exactly ONE thing: the generator's registered suffix,
   before the extension (`SITE_FILE_SUFFIX`: chatgpt `_gpt`, gemini
   `_gem`, api_image `_api`) —
   `<drop path>/<File>.png` → `<out>/<drop path>/<File>_<sfx>.png`
   (e.g. `masters/weeks/inner_wheel/mood/primary/colored/Glory.png`
   → `<out>/masters/weeks/inner_wheel/mood/primary/colored/Glory_gem.png`)
   — so a finished collection COPIES STRAIGHT into the consuming
   project's root, whatever that root is called. **Why this is a law:**
   until 2026-08-14 `dest_for` stripped a literal leading `assets`
   (true of every sheet the day it was written) and dumped anything
   else into a `<site>/` folder; the day Watch Academy renamed its
   tree to `masters/`, all 1145 already-generated images read as
   missing and the app offered to make them again. The guard is
   `tests/test_runner_paths_and_save.py::test_dest_for_keeps_the_sheets_path_exactly`.
   No
   approval step (owner 2026-07-17: saving IS the end of the
   tool's job). Run state + reports live under `<out>/_state/<site>/`
   and backup variants under `<out>/EXTRA/` — neither pollutes the
   copy-ready tree. An optional per-sheet **report txt**
   (`<stem>_report.txt`, on by default) logs run start/finish
   timestamps, per-image GENERATE time (AI: SEND -> image) and OUR
   time (save + bgfix + pause — "sve se računa"), original -> final
   resolution, file size, extra actions (REMOVE BG), the per-image
   averages and the collection total. The GUI Dashboard shows the
   same numbers live, per collection AND per whole run, with a
   collapsible history of finished collections. On a refusal the
   "safer retry" (ON by default) re-sends the item ONCE with a preamble
   chosen BY REFUSAL SCENARIO (owner 2026-07-23): the driver classifies
   the refusal into a category (`SiteConfig.refusal_markers` —
   `REFUSAL_SAFETY` / `REFUSAL_COPYRIGHT`, checked most-specific-first)
   and the runner prepends the matching `RETRY_PREAMBLES` entry — the
   allegory reframing (`SAFER_PREAMBLE`) for a safety block, the homage /
   editorial reframing (`COPYRIGHT_PREAMBLE`) for a copyright
   "third-party content" block (the Star Wars run — Yoda / Grand Moff
   Tarkin). A category with no preamble is reported without a retry.
   Then it moves on. (A prompt-sheet file is called a COLLECTION in
   the UI — a set of images, not always a theme.)
7b. **ONE generated-output root** (owner 2026-08-04): everything the
   program produces lives under `output/` —
   `output/images/` (`DEFAULT_OUT_DIR`, the copy-ready assets mirror
   with its `_state/` + `EXTRA/`) and `output/sheets/`
   (`SHEETS_DIR`, the New Collection (AI) wizard's `.md` files, a
   SIBLING so a sheets folder never travels with a copy of the
   images tree). `config.GENERATED_ROOT` is the ONE authority; the
   whole root is gitignored — one folder to ignore, back up or
   empty. Both remain freely overridable per run in the GUI (and by
   `--out` on the CLI); nothing is ever moved automatically, so a
   pre-2026-08-04 `out/`/`sheets/` folder simply stays where it is.
8. **Sources are READ ONLY.** The tool writes ONLY under the chosen
   output folder (images, progress sidecars, reports, background
   fixes) and never touches the sheet's folder. The `UV/` folder is
   the owner's private material — gitignored, never committed, read
   only when he points at it.

## The Generator Suffix Registry (owner 2026-07-22 — binding)

**Every image-generation tool/AI this project drives MUST have its
own filename suffix, registered BEFORE it generates a single image.**
The suffix is how a saved file names its generator (DOMY RESTRUCTURE
convention: `<Figure>[_vN]_<sfx>.png`, suffix ALWAYS terminal in the
stem) — an unregistered generator has nowhere valid to save to.

- **The ONE authority in code is `SITE_FILE_SUFFIX`** in
  `painter/config/paths.py` — `dest_for` (save path) and
  `ai.drop_and_site_for` (the reverse) both read it; no other place
  may define or hardcode a suffix.
- Adding a generator = one new `key: "_sfx"` entry there + a row in
  the table below. Suffixes are unique, short, lowercase,
  underscore-prefixed, and name the generator (not the model
  version).
- `dest_for` fails LOUDLY (KeyError) for a key with no suffix —
  that is the guard, never soften it.

| Generator (site key) | Suffix | Meaning |
|----------------------|--------|---------|
| `chatgpt` | `_gpt` | ChatGPT browser tab |
| `gemini` | `_gem` | Gemini browser tab |
| `api_image` | `_api` | Gemini image API (paid) |

Future API generators (e.g. Imagen, DALL·E as separate tools) each
get their OWN suffix (e.g. `_imgn`, `_dalle`) — `_api` stays with
the current single API job and is never shared.

## The Sheet Contract (the input format)

Per theme `.md` file:
1. The `# H1` names the theme.
2. Every image is a `**Bold heading** → \`assets/.../path.png\``
   line — the arrow line carries the FULL SITE-AGNOSTIC assets
   path (headings and paths may wrap). All 30 sheets migrated to
   this form 2026-07-18; the sheet-authoring contract lives in
   [instructions.md](instructions.md).
3. The FIRST fenced code block after that heading is the prompt —
   copied byte-identical into the chat box, plus the site's
   background suffix.
3b. An entry may ALSO carry OPTIONAL **input image(s)** (owner
   2026-07-23; MULTI + faza 2 binding, owner 2026-08-03): one or more
   `← \`refs/photo.png\`` lines under the arrow (mirror of the `→`
   output arrow), LINE ORDER = ATTACH ORDER ("the FIRST/SECOND
   attached image"). Each is a READ-ONLY source photo, resolved at run
   time in the BINDING order ① sheet's own folder → ② the run's
   **Reference folder** (the GUI Prompt+Image section) → ③ absolute,
   then ATTACHED into the composer before the prompt
   (`submit_with_image`, acting like a person: expand the "+" menu →
   pick the add-image option → set the file(s) → wait for the preview
   → send; the API job builds `inlineData` parts in the same order) —
   for "put THIS character into that scene" prompts and for REFERENCE
   SHEETS (the second sheet kind: the prompt describes everything
   EXCEPT the figure, the likeness arrives as the attachment — the
   starwars reference sheet is the canonical form). Any of
   `TOOL_IMAGE_EXTENSIONS` (png/jpg/jpeg/webp). A missing file is a
   loud per-item SKIP; the rest of the batch runs. **PROMPT + IMAGE
   mode** (the GUI toggle beside "Select images…", faza 2): ON = only
   entries with prompt AND every reference present generate — load
   all prompts plus 1 reference file and exactly 1 image runs; the
   excluded rest is loudly listed. See
   [instructions.md](instructions.md) rule 3c.
4. *(italic notes)* are skipped. Skip markers (REUSE / SUPERSEDED /
   DO-NOT-GENERATE, only inside `**bold**` spans; per entry, per
   section note, or per marked section heading) are **ADVICE, not
   law** (owner 2026-07-17): an entry that still carries a prompt
   LOADS as an item with the advice attached — the GUI unticks it
   by default and it runs only when explicitly ticked. Marked
   entries with NO prompt in the sheet (the REUSE seats) are just
   listed — there is nothing to load.
5. A heading the parser cannot pair with a prompt is REPORTED
   loudly (the fix belongs in the sheet, not in parser leniency).
6. The parser ALSO reads the pre-convention legacy forms
   (2026-07-17), best-effort and never loud: heading entries
   (`### Name (\`file.png\`)`), whole-paragraph bold tokens
   (`**Sun** — \`sun.png\``), and bare bold names under a section
   heading that carries a backticked drop dir (the astrology
   sheet). Legacy oddities — reuse pointers with duplicate or
   escaping paths, unpaired mentions — are silently ignored so old
   sheets never block a batch. The six sheets whose entries once
   carried NO filenames at all (intelligences, mood, sin, virtue,
   instrument, season_trinity) had the arrow-path added to every
   entry, 2026-07-17 — all six now `--dry-run` clean, 0 problems.

## The DOM States (keep in ONE config block, with fallbacks)

Selectors rot with every reskin — when none match, FAIL LOUDLY
(No Error Masking, [Code Rules](../../rules/CODE.md)), never guess.

- **ChatGPT** (verified against the live DOM by the owner,
  2026-07-17): prompt box `#prompt-textarea` (ProseMirror
  contenteditable). The composer button keeps the stable id
  `#composer-submit-button` and MORPHS by state: empty box =
  "Start Voice", text entered = `data-testid="send-button"`
  (`aria-label="Send prompt"`), WHILE GENERATING =
  `data-testid="stop-button"` (`aria-label="Stop answering"`) —
  the stop state's disappearance is the "done" edge. A response
  turn is `section[data-turn="assistant"]`
  (`data-testid="conversation-turn-N"`); the generated image sits
  in `div[id^="image-"]` (class `group/imagegen-image`) as
  `img[alt^="Generated image"]` whose `src` is an https
  `backend-api/estuary/content` signed URL (fetched in-page, with
  session cookies). Refusal/quota banner: not yet captured — the
  driver reports the response text loudly when no image appears.
  IMAGE-FAILURE states have TWO faces, both matched by
  `image_failed_text_markers` and both riding one recovery ladder
  (owner 2026-07-21 + 2026-07-23): (a) "Image generation failed / …
  reply with 'retry'" — its own suggested word; (b) the generic red
  error turn `<p>Hmm...something seems to have gone wrong.</p>` /
  "error on my side", which carries a native Retry BUTTON
  `button[data-testid="regenerate-thread-error-button"]`
  (`image_error_retry_button`) that regenerates in place. The ladder:
  click that button → paced "retry" text (random 1–3 min apart) →
  escalation rounds (wait → page REFRESH → NEW SESSION → whole
  prompt); every round exhausted STOPS the site.
- **Gemini** (verified against the live DOM by the owner,
  2026-07-17): prompt box `rich-textarea` >
  `div.ql-editor[contenteditable]` ("Ask Gemini"). Send and stop
  share ONE container — `div[data-test-id="send-button-container"]`
  > `gem-icon-button`: typing makes it visible with
  `aria-label="Send message"`; WHILE GENERATING it becomes class
  `stop` / `aria-label="Stop response"` (mat-icon `stop`) — that
  state's disappearance is the "done" edge. A response is
  `<model-response>`; the image sits under `generated-image` >
  `single-image` > `button.image-button` as an `img` with
  `alt=", AI generated"` and a `blob:` src (fetched in-page).
  Response-text markers split TWO ways (owner 2026-07-17, after a
  live Gemini safety refusal): SAFETY REFUSAL of one prompt (e.g.
  "can't generate unsafe images", Serbian variants too) skips THAT
  ITEM — reported in log + report txt, run continues, a rerun
  retries it (the owner may also intervene manually — replying
  "MAKE IT SAFER" in the tab often regenerates). QUOTA/RATE-LIMIT
  markers are TERMINAL for the whole site — report and stop, never
  blind-retry (EN + Serbian; ChatGPT's "hit the Plus plan limit /
  limit resets" and Gemini's "limit resets / check your usage" both
  captured live 2026-07-17). Unknown no-image states stay loud
  DriverErrors.

## The Run Loop

**F1 REWORK LANDED (owner 2026-07-29, [REWORK.md](REWORK.md)):** the
per-item mechanics below are now TURN-BASED — the driver snapshots a
pre-submit `Baseline` (assistant-turn count + last image src), clears
the composer only when non-empty, VERIFIES the typed text, CONFIRMS
the send (composer emptied + our text as the newest user turn, via
`SiteConfig.user_turn`), and "done" = a NEW assistant turn holding a
loaded image with a fresh src (the busy button is secondary — a stuck
stop button can no longer stall or mis-attribute a result). Unmatched
TEXT answers loud-skip the item (`NoImage.had_text` — the continue
nudge fires ONLY on truly empty answers); a refusal inside the
image-failed ladder skips the item instead of stopping the site; a
byte-identical result to the previous save is re-submitted once then
loud-skipped (the duplicate-save bug). **F1b (owner 2026-08-04, the
Padmé/Qui-Gon incident):** the result is additionally ANCHORED to our
own user turn — accepted only when it FOLLOWS it in the DOM (turn
COUNTS lie in long chats: the site virtualizes old turns away); a
confirmed message the site then silently DROPS raises `SendVanished`
and the runner re-sends the item's OWN prompt once — NEVER the
content-blind continue nudge, which regenerated the PREVIOUS request
and saved a Qui-Gon badge as `Padme_v3_gem.png`; and a safer retry's
own failure of ANY per-item kind skips the item instead of stopping
the site (the 18:43:46 ChatGPT stop). Details in
[CDP Driver](painter/__about/driver.md) and [Run Loop](painter/__about/runner.md).

`parse(sheet) → queue` → per pending item: paste (+ suffix) →
submit → await the done-edge (hard timeout) → extract bytes → save
`<out>/<rest>/<File>_gem|_gpt|_api.png` (the assets mirror — DOMY
RESTRUCTURE 2026-07-22: the generator is a terminal FILENAME suffix
per `SITE_FILE_SUFFIX`, no per-site folders) → background
fix → pause → next. An `ImageGenFailed` (either ChatGPT face) triggers
the RECOVERY LADDER (owner 2026-07-23): native Retry button → paced
"retry" text (random 1–3 min apart, `IMAGE_FAILED_RETRY_MAX` times) →
escalation rounds (`IMAGE_FAILED_ESCALATION_DELAYS_S`, default 1–3 min
then 22–36 min: wait → REFRESH → NEW SESSION → whole prompt). Every
wait polls Stop. The first rung that yields an image continues the run;
exhausting all rungs STOPS the site (no per-item skip for this failure)
— resume is by the files already on disk. Progress logging per item
(elapsed, done/total — Progress Logging for Long Tasks,
[Code Rules](../../rules/CODE.md)). **DONE = the FILE EXISTS at its output path**
(`<out>/dest_for(...)`), checked on disk — not a sidecar record
(the `.progress.json` state file was removed 2026-07-19). RESUMABLE
for free: the folder is ALWAYS the source of truth (owner 2026-07-21)
— an unattended run skips items whose dest file already exists, and
NO file on disk is EVER overwritten. An EXPLICIT tick on a done item
is a deliberate REDO (owner 2026-07-27): it generates again and
saves as the NEXT `_vN` sibling per the DOMY rotation convention —
`<File>[_vN]_<sfx>.png`, version BEFORE the terminal generator
suffix, canonical file = v1, first redo = `_v2`, and with `_v4` on
disk the next is `_v5` (`config.versioned_dest_for` scans the dest
folder; the owner's irregular `_v`/`_v1` forms read as v1). Select
shows done items green and re-tickable — tick = new version, the
saved image stays. Every `item_progress`/`item_done` event carries
`rel`, the ACTUAL saved path, so the dashboard, parallel checker and
fixer follow the version file (and `ai.drop_and_site_for` strips
`_vN`, so a flagged version re-sends through its own sheet entry —
which then lands as the NEXT version). At
the end the owner reviews
quality; unsatisfying prompts get reworked in the sheet or re-ticked.

**TRANSCRIPT + REFUSAL DIAGNOSTIC (owner 2026-08-11):** every text the
site answers is appended verbatim to
`<out>/_state/<site>/transcript.jsonl` (`painter/transcript.py` —
event, full raw text, matched category or `null`, action taken), so a
new unknown site state is diagnosed FROM THE RECORD instead of by
re-provoking the failure live (`matched: null` rows are where new
markers are mined from). And when a refusal survives the safer retry,
the runner asks the site ONE text-only question
(`REFUSAL_DIAGNOSTIC_QUESTION` — which specific element trips the
policy?) instead of a third blind attempt; the answer lands in the
transcript, the report txt (`WHY (site's answer)` line) and the
`item_refused` event, and the Dashboard's double-click viewer shows
the ACTUAL refusal message + that answer where the image would be.
Both are best-effort diagnostics — they never fail or stop a run.

**GitHub:** [UVuruna/Prompt-Painter](https://github.com/UVuruna/Prompt-Painter)
(`origin`, branch `main`).

## Build Order (steps 1–3 built 2026-07-17; GUI layer the same day)

1. **The sheet parser first** — pure, offline-testable against the
   REAL sheets in `../Watch Academy/research/prompts/archetype/`
   (golden tests: file → expected (name, path, prompt) tuples,
   REUSE skipping, unpaired-heading reporting).
2. The CDP driver second (config block of selectors, the done-edge
   watcher, the blob extractor).
3. The loop + state file + pacing.
4. The GUI + Chrome launcher + background-fix integration.

## Honesty Notes (tell the owner, never hide)

- Driving the consumer web UIs breaches both sites' automation
  clauses. This is a CONTRACT matter, not law: the realistic
  consequences are account-level only (captcha walls, rate limits,
  temporary or permanent account suspension). The owner accepts
  the risk for his volume; the tool's duty is to be POLITE (paced,
  one window per site, supervised) and to stop on any block
  signal. If his Gemini runs on his main Google account, suggest a
  secondary account for peace of mind. The clean alternative if
  volume grows: the official image APIs (pay-per-image).
- The dedicated `chrome-profile/` holds live Google/OpenAI session
  cookies on disk — treat the folder as a credential store (it is
  gitignored; never copy it around).
