# DECISIONS — PromptPainter

Owner decrees and binding design decisions, with their dates. Moved out of
`CLAUDE.md` (2026-08-18, byte-diet) to keep the project file under the 6 KB
constitution limit. Read this when you need the WHY behind a behavior;
`CLAUDE.md` states only WHAT and points here. Sheet-authoring detail lives in
[`instructions.md`](../instructions.md); the live DOM protocol lives in
[`PROTOCOL.html`](../PROTOCOL.html) — neither is repeated here.

## Core mechanic (owner 2026-07-16 — do not relitigate)

- **Mechanic:** ★ CDP ATTACH — Chrome runs with
  `--remote-debugging-port=9222`; the tool attaches with
  `playwright.chromium.connect_over_cdp` and drives the DOM. NO browser
  extension, NO OCR, NO virtual mice (extension = plan B if a site blocks
  CDP; MouseMux = plan C of last resort).
- **No Download clicks:** when the response `<img>` appears, read the image
  BYTES from the DOM inside `page.evaluate` — CANVAS-FIRST (`drawImage` +
  `toDataURL`, since Gemini's CSP blocks `fetch()` of `blob:` srcs; always
  yields real PNG), `fetch()` as fallback — and save the file DIRECTLY under
  the sheet's filename; there is no rename/move step.
- **Supervised runs:** the owner watches the windows, at least until the
  tool has proven itself; paced (configurable pause between prompts).

## The Workflow (owner 2026-07-17, tightened through 2026-08-14)

- `python main.py` — no arguments opens the GUI; sheet arguments run the
  single-site CLI.
- Queue ONE OR MORE sheet `.md` files + an output folder. Each site works
  the queue in order; a quota stop mid-batch never costs finished work.
  "Select images…" is PER SITE; a done item shown green is re-tickable —
  ticking it REDOES it as the next `_vN` version (owner 2026-07-27).
  **Prompt + Image** toggle (faza 2, owner 2026-08-03) narrows the run to
  complete prompt+reference pairs. "BG removal only…" runs the background
  remover standalone over any existing folder.
- Sites: Gemini, ChatGPT, or BOTH IN PARALLEL — one window/thread per site,
  never parallel hammering of the same site.
- Chrome launches with the project's own profile (`chrome-profile/`,
  gitignored) since Chrome 136+ refuses CDP on the default profile — the
  owner logs in there once.
- Per-site background suffix (dropdown: `transparent`/`white`/`none`,
  ChatGPT default transparent, Gemini default white). Gemini prompts always
  carry the NO-reflections law (2026-07-17); ChatGPT prompts always carry
  the ANTI-GRAIN law (2026-07-27, the Voljin_gpt case). The old
  keyword-inferred aspect-ratio law was REMOVED (2026-07-22) — the sheet
  author states aspect/shape/background explicitly (`instructions.md` rule
  3b); the tool never infers it from prompt text.
- **Postprocess hook** after every save, three composable steps, all ON by
  default (owner 2026-07-18): `remove_background` (in-house
  `painter/bg_remove.py`, moved from Watch Academy 2026-07-17 — no part of
  this program lives in another project; AUTO mode detects
  transparent/white/black/agreeing-corners per file, owner 2026-07-28, or a
  FORCED/CUSTOM colour ± X % per channel with a FLOOD-FILL-from-frame vs.
  "everywhere" reach choice), `crop_transparent`, `upscale_if_small`
  (Real-ESRGAN ncnn-vulkan, aspect 0.9–1.1 AND under 800 px only). Failures
  are loud but never kill the run.
- **THE PATH IN THE SHEET IS THE PATH** (owner decree 2026-08-14, binding,
  supersedes the 2026-07-18/22 "assets mirror" wording): PromptPainter
  appends exactly ONE thing to the sheet's own path — the generator's
  registered suffix before the extension. It never reads a root out of the
  path, strips a segment, or invents a folder — so a finished collection
  copies straight into the consuming project's root, whatever it is called.
  **Why this is a law:** until 2026-08-14 `dest_for` stripped a literal
  leading `assets` and dumped anything else into a `<site>/` folder; the day
  Watch Academy renamed its tree to `masters/`, all 1145 already-generated
  images read as missing and the app offered to regenerate them. Guard:
  `tests/test_runner_paths_and_save.py::test_dest_for_keeps_the_sheets_path_exactly`.
- No approval step — saving IS the end of the tool's job (owner 2026-07-17).
  Run state + reports live under `<out>/_state/<site>/`, backup variants
  under `<out>/EXTRA/`. Per-sheet report txt + live Dashboard numbers
  (elapsed, GENERATE vs OUR time, resolution, size, extra actions,
  per-image and collection averages). "Safer retry" (ON by default)
  re-sends a refused item ONCE with a preamble chosen BY REFUSAL SCENARIO
  (owner 2026-07-23) — `SiteConfig.refusal_markers` classify,
  `RETRY_PREAMBLES` supplies the text; an unmapped category is reported
  without a retry.
- **ONE generated-output root** (owner 2026-08-04): `output/images/`
  (`DEFAULT_OUT_DIR`) + `output/sheets/` (`SHEETS_DIR`, sibling so a sheets
  folder never travels with the images tree). `config.GENERATED_ROOT` is
  the one authority; the whole root is gitignored. Both overridable per
  run; nothing pre-2026-08-04 is ever moved automatically.
- **Sources are READ ONLY** — the tool writes only under the chosen output
  folder and never touches the sheet's own folder.

## The Generator Suffix Registry (owner 2026-07-22, binding)

Every image-generation tool/AI this project drives MUST have its own
filename suffix, registered BEFORE it generates a single image — the
suffix is how a saved file names its generator
(`<Figure>[_vN]_<sfx>.png`, suffix always terminal in the stem).

- **The ONE authority in code is `SITE_FILE_SUFFIX`** in
  `painter/config/paths.py` — `dest_for` (save path) and
  `ai.drop_and_site_for` (the reverse) both read it; no other place may
  define or hardcode a suffix. `dest_for` fails LOUDLY (KeyError) for an
  unregistered key.
- Adding a generator = one new `key: "_sfx"` entry + a table row below.
  Suffixes are unique, short, lowercase, underscore-prefixed, name the
  generator (not the model version).

| Generator (site key) | Suffix | Meaning |
|----------------------|--------|---------|
| `chatgpt` | `_gpt` | ChatGPT browser tab |
| `gemini` | `_gem` | Gemini browser tab |
| `api_image` | `_api` | Gemini image API (paid) |

Future API generators (Imagen, DALL·E as separate tools) each get their OWN
suffix (e.g. `_imgn`, `_dalle`) — `_api` stays with the current single API
job and is never shared.

## The Sheet Contract

The full authoring contract (H1, arrow-path entries, prompt code block,
optional `←` reference images, skip markers, legacy forms) is
[`instructions.md`](../instructions.md) — that file IS the spec, written for
sheet authors. Binding decisions layered on top of it:

- **PROMPT + IMAGE mode** (faza 2, owner 2026-08-03): ON = only entries with
  a prompt AND every reference present generate; the excluded rest is
  loudly listed. Attach order = `←` line order; resolution order ①
  sheet's own folder → ② the run's Reference folder → ③ absolute.
- Skip markers (REUSE/SUPERSEDED/DO-NOT-GENERATE) are ADVICE, not law
  (owner 2026-07-17) — an entry with a prompt still loads, unticked by
  default.

## The DOM protocol

Selectors rot with every reskin — kept in ONE config block
(`painter/config/sites.py`) with fallbacks, FAIL LOUDLY when none match
(No Error Masking, [Code Rules](../../../rules/CODE.md)). The full
turn-based protocol (baseline/type/send/await/extract, the recovery ladder,
refusal classification) is diagrammed in
[`PROTOCOL.html`](../PROTOCOL.html) — read that before touching
`painter/driver.py` or `painter/runner.py`.

Binding decisions not obvious from the diagram:
- **F1 turn-based protocol LANDED 2026-07-29**: done = a NEW assistant turn
  holding a loaded image with a fresh src (image wins; the busy button is
  secondary).
- **F1b anchoring (owner 2026-08-04, the Padmé/Qui-Gon incident):** the
  result is additionally ANCHORED to our own user turn (turn COUNTS lie in
  long chats — sites virtualize old turns away); a confirmed message the
  site then silently drops raises `SendVanished` and the runner re-sends
  the item's OWN prompt once — never the content-blind continue nudge.
- **DONE = the FILE EXISTS at its output path**, checked on disk (the
  `.progress.json` sidecar was removed 2026-07-19) — the folder is always
  the source of truth (owner 2026-07-21), so an unattended run skips items
  already on disk and never overwrites. An EXPLICIT tick on a done item is
  a deliberate REDO (owner 2026-07-27): saves as the next `_vN` sibling.
- **TRANSCRIPT + REFUSAL DIAGNOSTIC (owner 2026-08-11):** every site answer
  is appended verbatim to `<out>/_state/<site>/transcript.jsonl`
  (`painter/transcript.py`); when a refusal survives the safer retry, the
  runner asks the site ONE text-only diagnostic question instead of a
  third blind attempt. Both best-effort — never fail or stop a run.

## Honesty notes (tell the owner, never hide)

- Driving the consumer web UIs breaches both sites' automation clauses —
  a CONTRACT matter, not law: realistic consequences are account-level only
  (captcha, rate limits, suspension). The owner accepts the risk for his
  volume; the tool's duty is to be POLITE (paced, one window per site,
  supervised) and to stop on any block signal. The clean alternative if
  volume grows: the official image APIs (pay-per-image).
- `chrome-profile/` holds live Google/OpenAI session cookies on disk —
  treat it as a credential store (gitignored, never copy it around).

## Open items

- **H1 crash** (double-click a dashboard folder → long view): not
  reproducible on demand; mitigated + instrumented (incremental render,
  top-level error logging). NOT declared fixed until a run reproduces or a
  month of runs stays clean.
- **Gemini copyright category:** generic-guidelines refusals classify as
  SAFETY until a distinctly-copyright Gemini text is captured live; then a
  `REFUSAL_COPYRIGHT` marker group is added.
- **`no_empty_space` helper wording** ships DEFAULT OFF until the owner
  approves/retunes the text (`PROMPT_HELPERS`, pure data).
- **God-file debt (Rule #20, root round DONE 2026-07-30):** the remaining
  documented RATCHET entries (`gui/app_jobs.py`, `painter/driver.py`,
  `gui/agent_panel.py` + five test modules) are owed a second split round —
  see the RATCHET list in `CLAUDE.md` → Project laws.
- **UI-SKETCH.md** is implemented and verified on a live window
  (2026-07-30) but stays as a reference file — the owner has not signed off
  closing it out.

See [`history/PLAN-2026-07-16.md`](history/PLAN-2026-07-16.md) (original
brief) and [`history/REWORK-2026-07-29.md`](history/REWORK-2026-07-29.md)
(the big rework — all seven phases LANDED) for the fully-landed design
documents this file summarizes.
