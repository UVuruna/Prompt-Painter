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

The full design discussion lives in DOMY Watch
`research/image_automation_plan.md` — this file is the binding spec.

## Decisions Already Made (owner 2026-07-16 — do not relitigate)

- **Name:** PromptPainter. **Stack:** Python + `playwright`.
- **Mechanic:** ★ CDP ATTACH — Chrome runs once with
  `--remote-debugging-port=9222`; the tool attaches with
  `playwright.chromium.connect_over_cdp` to the user's real,
  logged-in profile and drives the DOM. NO browser extension, NO
  OCR, NO virtual mice (extension = plan B if a site blocks CDP;
  MouseMux = plan C of last resort).
- **No Download clicks:** when the response `<img>` appears, read
  the image BYTES from the DOM (fetch its `blob:`/`data:` src
  inside `page.evaluate`, return base64) and save the file
  DIRECTLY under the sheet's filename into `out/<theme>/` — the
  tool names files itself; there is no rename/move step.
- **Supervised runs only:** the owner watches the window; paced
  (configurable pause between prompts); ONE window, never parallel.

## The Sheet Contract (the input format)

Per theme `.md` file:
1. The `# H1` names the theme.
2. Every image is a `**Bold heading** → \`drop/path.png\`` line —
   the arrow line carries the OUTPUT FILENAME.
3. The FIRST fenced code block after that heading is the prompt —
   copied byte-identical into the chat box.
4. *(italic notes)* are skipped; entries marked REUSE or
   DO-NOT-GENERATE are logged as skipped, never generated.
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

`parse(sheet) → queue` → per pending item: paste → submit → await
the done-edge (hard timeout) → extract bytes → save
`out/<theme>/<stem>.png` → mark done in `.progress.json`
(RESUMABLE — a crash or quota stop costs nothing) → pause → next.
Progress logging per item (elapsed, done/total — root Rule #10).

## Build Order

1. **The sheet parser first** — pure, offline-testable against the
   REAL sheets in `../DOMY Watch/research/prompts/archetype/`
   (golden tests: file → expected (name, path, prompt) tuples,
   REUSE skipping, unpaired-heading reporting).
2. The CDP driver second (config block of selectors, the done-edge
   watcher, the blob extractor).
3. The loop + state file + pacing last.

## Honesty Notes (tell the owner, never hide)

- Driving the consumer web UIs breaches both sites' automation
  clauses. This is a CONTRACT matter, not law: the realistic
  consequences are account-level only (captcha walls, rate limits,
  temporary or permanent account suspension). The owner accepts
  the risk for his volume; the tool's duty is to be POLITE (paced,
  single window, supervised) and to stop on any block signal.
  If his Gemini runs on his main Google account, suggest a
  secondary account for peace of mind. The clean alternative if
  volume grows: the official image APIs (pay-per-image).
