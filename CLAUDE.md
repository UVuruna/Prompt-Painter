# CLAUDE.md — PromptPainter

Project-specific guidance for Claude Code. **Inherits ALL rules from
the monorepo root [CLAUDE.md](../../CLAUDE.md)** — read that first.
Communicate with the owner in Serbian (Latin); everything in files
stays English.

---

## What This Project Is

A supervised automation tool that GENERATES IMAGES from the owner's
prompt-sheet `.md` files by driving his ALREADY OPEN, already
logged-in Gemini/ChatGPT browser tab: paste a prompt, wait for the
generation to finish, capture the image, save it under the sheet's
own filename into the theme's folder. The sheets live in his other
projects (first consumer: DOMY Watch `research/prompts/`); this tool
only consumes them.

The full design discussion lives in [PLAN.md](PLAN.md) — this file
is the binding spec.

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
   already-done items show disabled. **"BG removal only..."**
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
   owner's three laws in EVERY prompt** (2026-07-17, after the
   rondel_Dawn/rondel_Shield drift): the ASPECT RATIO law — picked
   from the prompt itself: badges/rondels/medallions = exactly
   1:1, TALL/lancet window prompts = tall portrait (config
   keyword rules) — the background rule, and absolutely NO
   reflections.
6. After every save, the **background fix** runs —
   `painter/bg_remove.py`, IN-HOUSE (moved from DOMY Watch tools,
   owner 2026-07-17: no part of this program lives in another
   project). It auto-detects per file — already-transparent
   skipped, white cleared + autocropped, ambiguous reported and
   left untouched. Failures are loud but never kill the run.
7. Images save **DIRECTLY** into a tree that MIRRORS DOMY's
   `assets/` (owner 2026-07-18): sheets carry FULL site-agnostic
   paths (`assets/emblem/mood/Glory.png`) and the tool injects the
   site after the category —
   `assets/<category>/<rest>` → `<out>/<category>/<site>/<rest>`
   (e.g. `out/emblem/gemini/mood/Glory.png`) — so a finished
   collection COPIES STRAIGHT into `DOMY Watch/assets/`. No
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
   collapsible history of finished collections. On a SAFETY refusal
   the "safer retry" (ON by default) re-sends the item ONCE with an
   allegory-framing preamble (config `SAFER_PREAMBLE`) before giving
   up, then moves on. (A prompt-sheet file is called a COLLECTION in
   the UI — a set of images, not always a theme.)
8. **Sources are READ ONLY.** The tool writes ONLY under the chosen
   output folder (images, progress sidecars, reports, background
   fixes) and never touches the sheet's folder. The `UV/` folder is
   the owner's private material — gitignored, never committed, read
   only when he points at it.

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
(root Rule #1), never guess.

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

`parse(sheet) → queue` → per pending item: paste (+ suffix) →
submit → await the done-edge (hard timeout) → extract bytes → save
`<out>/<category>/<site>/<rest>` (the assets mirror) → background
fix → mark done in
`.progress.json` (RESUMABLE — a crash or quota stop costs nothing)
→ pause → next. Progress logging per item (elapsed, done/total —
root Rule #10). At the end the owner reviews quality; unsatisfying
prompts get reworked in the sheet.

**GitHub:** [UVuruna/Prompt-Painter](https://github.com/UVuruna/Prompt-Painter)
(`origin`, branch `main`).

## Build Order (steps 1–3 built 2026-07-17; GUI layer the same day)

1. **The sheet parser first** — pure, offline-testable against the
   REAL sheets in `../DOMY Watch/research/prompts/archetype/`
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
