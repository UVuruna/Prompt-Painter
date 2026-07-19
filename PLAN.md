# PLAN.md — the Design Discussion (companion to CLAUDE.md)

This is the full design discussion that produced the binding spec in
[CLAUDE.md](CLAUDE.md). The agent building this project reads
CLAUDE.md FIRST (it loads automatically); this file carries the
reasoning, alternatives and trade-offs behind those decisions.

---

The owner's ask (2026-07-16): a program that reads our prompt-sheet
`.md` files, extracts the theme and the image prompts, and drives an
OPEN Gemini/ChatGPT browser window — paste prompt, wait for the
generation to finish (the send button's state), save the image,
name it after the prompt's title, and file everything under the
theme's folder. This document is the design proposal.

## Verdict on WHERE: a NEW standalone project

**Recommendation: a separate project** (e.g. `Gadgets/PromptPainter`),
not inside DOMY Watch:

- It is a GENERAL tool — it serves every project's sheets, not just
  this dial's; DOMY stays the data (the sheets), the tool is the
  machine that eats them.
- Different runtime (Node or Python + Playwright, browser plumbing)
  — nothing DOMY's purity tests or build should ever see.
- Per the monorepo rules it gets its own README/PROJECTS.md entry.
- DOMY only guarantees the SHEET CONTRACT below.

## Verdict on HOW: CDP attach — no extension, no OCR, no mice

Three candidate mechanics, ranked:

1. ★ **CDP attach (Playwright `connect_over_cdp`)** — the user's
   REAL Chrome starts once with `--remote-debugging-port=9222`; the
   tool attaches to the ALREADY LOGGED-IN tab and drives the DOM
   directly. No extension to build/package, no injection tricks, no
   pixels. Everything the owner described — reading the button
   state, taking the last response — becomes a `querySelector` +
   a wait.
2. **Browser extension (content script)** — workable but strictly
   more moving parts (manifest v3, packaging, messaging to a local
   process for file writes). Plan B if CDP attach trips a site's
   automation detection.
3. **MouseMux/virtual mice + OCR** — plan C only: pixel-state
   reading is brittle against every UI reskin, and two virtual mice
   fight the user for the desktop. Keep as the fallback of last
   resort; a DOM+mice hybrid buys nothing once CDP works.

**The killer simplification: DO NOT click Download at all.** Once
the response's `<img>` appears, the tool reads the image BYTES
straight from the DOM (fetch the `blob:`/`data:` src inside
`page.evaluate`, return base64) and SAVES THE FILE ITSELF — under
the exact name from the sheet (`Jesus_Advocate.png`), straight into
`out/<theme>/`. The owner's whole download-watch → rename → move
pipeline disappears; naming is ours from the start.

## The DOM states we watch (per site, verified at build time)

Selectors rot — the tool keeps them in ONE config block with
fallbacks, and fails LOUDLY when none match (house Rule #1).

- **ChatGPT:** prompt = the `#prompt-textarea` contenteditable;
  send = `button[data-testid="send-button"]` (disabled while empty,
  replaced by `data-testid="stop-button"` WHILE GENERATING — its
  disappearance is the "done" edge); the result = the last
  `article` turn's `img` nodes (wait until non-placeholder, src
  reachable).
- **Gemini:** prompt = the `rich-textarea` contenteditable; send =
  `button[aria-label*="Send"]` (aria-disabled toggles; a stop state
  appears while running); the result = the last `model-response`'s
  `img` (generated-image node). Quota/refusal banners are terminal
  states the tool must recognize and report, not retry blindly.

The "ready for a new prompt" condition the owner described — the
send button returning to its idle-enabled state — is exactly the
edge both sites expose; we poll/observe it with a hard timeout.

## The sheet contract (our .md files already comply)

The parser expects, per theme file:

1. The `# H1` names the theme (and the sheet's register).
2. Every image is a `**Bold heading** → \`drop/path.png\`` line —
   the ARROW LINE carries the output filename.
3. The FIRST fenced code block after that heading is the prompt,
   copied byte-identical (house rule: prompts move verbatim).
4. *(italic notes)*, REUSE and DO-NOT-GENERATE markers are skipped
   (REUSE entries are logged as skipped, never generated).

The archetype sheets already follow this exactly; older weekday
sheets very nearly (the parser reports any heading it could not
pair with a prompt — the fix is in the sheet, not the parser).

## The run loop

queue = parse(sheet) → for each pending item: paste, submit, await
the done-edge, extract bytes, save `out/<theme>/<stem>.png` →
RESUMABLE for free because DONE = the output file EXISTS on disk (a
run skips items whose file is already there; the `.progress.json`
sidecar was dropped 2026-07-19); paced (a configurable pause
between prompts — image quotas are real); always supervised, the
owner watching the window it drives.

## Honesty notes

- Driving the consumer web UIs is against both sites' automation
  clauses; it is the owner's own account and his own supervised
  session, but a flag/temporary block is possible — the tool must
  be polite (paced, one window, no parallel hammering). The CLEAN
  alternative exists: the official image APIs (Imagen / gpt-image)
  — pay-per-image, zero UI fragility; worth pricing out if volume
  grows.
- Selector maintenance is a fact of life: both UIs reskin often;
  the config-block-with-fallbacks + loud failure is the design
  answer.

## Open for the owner

1. New project name (proposal: **PromptPainter**; alternatives:
   Easel, ArtLine).
2. Node (Playwright's home turf) or Python (his stack) — both
   fine; proposal: **Python + playwright** for house consistency.
3. GO to scaffold the project skeleton + the sheet parser first
   (testable offline against our real sheets), browser driver
   second.
