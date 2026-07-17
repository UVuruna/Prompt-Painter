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
  the image BYTES from the DOM (fetch its `blob:`/`data:` src
  inside `page.evaluate`, return base64) and save the file
  DIRECTLY under the sheet's filename — the tool names files
  itself; there is no rename/move step.
- **Supervised runs:** the owner watches the windows, at least
  until the tool has proven itself; paced (configurable pause
  between prompts).

## The Workflow (owner 2026-07-17 — supersedes where it differs)

1. The owner starts the **GUI** (`python gui.py`) — the usual front
   door; the CLI (`python main.py`) stays for single-site runs.
2. He picks the sheet `.md` and the OUTPUT folder.
3. He picks the sites: **Gemini, ChatGPT, or BOTH IN PARALLEL** —
   one window and one thread per site, each at its own pace (this
   amends the older one-window rule: still ONE window PER SITE,
   never parallel hammering of the same site).
4. The tool opens the automation Chrome itself (button / pre-run
   check). **Chrome 136+ refuses CDP on the default user profile**,
   so it launches with the project's own profile folder
   (`chrome-profile/`, gitignored) — the owner logs in there ONCE;
   sessions persist across runs.
5. Every prompt gets the site's **background suffix** appended
   (config): ChatGPT is asked for a fully TRANSPARENT background,
   Gemini for a flat PURE WHITE one.
6. After every save, the **background fix** runs (DOMY Watch
   `tools/bg_remove.py`, subprocess): it auto-detects per file —
   already-transparent skipped, white cleared, ambiguous reported
   and left untouched. Failures are loud but never kill the run.
7. Output layout: **`<out>/<site>/<drop-path>`** (e.g.
   `out/gemini/trinity/Jesus_Advocate.png`) — the arrow line's own
   path IS the theme folder; the per-site split keeps parallel runs
   collision-free and matches DOMY's per-source asset trees.
8. **Sources are READ ONLY.** The tool writes ONLY under the chosen
   output folder (images, progress sidecar, background fixes) and
   never touches the sheet's folder. The `UV/` folder is the
   owner's private material — gitignored, never committed, read
   only when he points at it.

## The Sheet Contract (the input format)

Per theme `.md` file:
1. The `# H1` names the theme.
2. Every image is a `**Bold heading** → \`drop/path.png\`` line —
   the arrow line carries the OUTPUT FILENAME (headings and paths
   may wrap; the drop path is used verbatim under `<out>/<site>/`).
3. The FIRST fenced code block after that heading is the prompt —
   copied byte-identical into the chat box, plus the site's
   background suffix.
4. *(italic notes)* are skipped; entries marked REUSE or
   DO-NOT-GENERATE are logged as skipped, never generated — the
   markers count only inside `**bold**` spans, and work per entry,
   per section note, or per marked section heading.
5. A heading the parser cannot pair with a prompt is REPORTED
   loudly (the fix belongs in the sheet, not in parser leniency).

## The DOM States (keep in ONE config block, with fallbacks)

Selectors rot with every reskin — when none match, FAIL LOUDLY
(root Rule #1), never guess.

- **ChatGPT:** prompt box `#prompt-textarea` (contenteditable);
  send `button[data-testid="send-button"]`; WHILE GENERATING it is
  replaced by `data-testid="stop-button"` — the stop button's
  disappearance is the "done" edge; result = the last `article`
  turn's `img` nodes (wait until a real src, not a placeholder).
- **Gemini:** prompt box the `rich-textarea` contenteditable; send
  `button[aria-label*="Send"]` (aria-disabled toggles; a stop state
  shows while running); result = the last `model-response`'s
  generated `img`. Quota/refusal banners are TERMINAL states —
  report and stop the item, never blind-retry.

## The Run Loop

`parse(sheet) → queue` → per pending item: paste (+ suffix) →
submit → await the done-edge (hard timeout) → extract bytes → save
`<out>/<site>/<drop-path>` → background fix → mark done in
`.progress.json` (RESUMABLE — a crash or quota stop costs nothing)
→ pause → next. Progress logging per item (elapsed, done/total —
root Rule #10). At the end the owner reviews quality; unsatisfying
prompts get reworked in the sheet.

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
