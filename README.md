# PromptPainter

<img src="assets/logo.svg" width="96" align="right">

A supervised image-generation runner built for unattended batches:
queue one or more prompt-sheet `.md` files, and it drives the
owner's logged-in Gemini and/or ChatGPT tabs over CDP — both in
parallel — captures each generated image straight from the DOM,
clears its background, and files it DIRECTLY as
`<out>/<site>/<drop-path>` with a per-sheet report. Named by the
sheet, resumable, paced, sources strictly read-only.

**Status:** live — first supervised runs succeeded 2026-07-17.
**GitHub:** [UVuruna/Prompt-Painter](https://github.com/UVuruna/Prompt-Painter)
**The handover pack: [CLAUDE.md](CLAUDE.md)** (the BINDING spec —
decisions, workflow, DOM states, build order) **+
[PLAN.md](PLAN.md)** (the design discussion behind it) **+
[REWORK.md](REWORK.md)** (the BIG REWORK plan, owner Q&A
2026-07-29 — wins over older CLAUDE.md sections until folded in) **+
[UI-SKETCH.md](UI-SKETCH.md)** (the setup-screen layout reference,
implemented and verified 2026-07-30).
First consumer: DOMY Watch prompt sheets.

## Structure

```
📁 PromptPainter/
  🐍 main.py            ← THE entry point (no args: GUI; sheets: CLI)
  📁 __about/               ← root-level file docs (main.py)
  📁 __flow/                ← root-level flow diagrams (main.py)
  📁 gui/                ← the tkinter window (main.py opens it)
    📝 ___gui.md            file index — mixins, widgets, theming
    📁 __about/ · 📁 __flow/
    📁 tool_panels/         ← the standalone-tool settings panels
  ⚙️ requirements.txt   ← playwright, numpy/scipy/pillow, pytest
  📁 assets/
    🖼️ logo.svg
  📁 painter/           ← config, parser, driver, loop, chrome,
    📝 ___painter.md       bg remover, postprocess
    📁 __about/ · 📁 __flow/
    📁 config/             ← every tunable, split by domain
    📁 ai/                 ← AI client, sheet flow, checks, flags
    🐍 sheet_parser.py
    🐍 driver.py
    🐍 runner.py
    🐍 chrome.py
    🐍 bg_remove.py
    🐍 postprocess.py
  📁 setup/             ← build orchestrator, cert, NSIS, ICO
    📝 ___setup.md
  📁 tests/             ← golden parser tests + offline loop tests
    📝 ___tests.md
    📁 fixtures/
  📁 output/            ← EVERYTHING the program generates (gitignored)
    📁 images/          ← the copy-ready assets/ mirror + progress + reports
    📁 sheets/          ← the AI-generated prompt sheets
  📁 chrome-profile/    ← the automation Chrome profile (gitignored)
  📁 UV/                ← the owner's private material (gitignored)
```

## Documentation

- [**Protokol razgovora sa sajtom**](PROTOCOL.html) — the whole
  per-item conversation protocol on ONE page (open it in a browser):
  the main loop and its three exits, phases 0–6, every branch
  `painter/driver.py` and `painter/runner.py` recognise with its exact
  action and outcome (Done / Oporavak / Skip stavke / Stop sajta), the
  invariants, and the incident that put each rule there. The
  module-level detail lives in [CDP Driver](painter/__about/driver.md)
  and [Run Loop](painter/__about/runner.md)
- [Sheet-authoring instructions](instructions.md) — the contract a
  sheet author (person or agent) follows; also behind the GUI's
  **Instructions** button
- [Painter (folder)](painter/___painter.md) — the engine package:
  [Config (subfolder)](painter/config/___config.md),
  [AI (subfolder)](painter/ai/___ai.md), plus the sheet parser, CDP
  driver, run loop, Chrome launcher, background remover and
  postprocess modules (see the folder doc's file table)
- [GUI (folder)](gui/___gui.md) — the window, the sheet queue, the
  threading, and the [Tool Panels (subfolder)](gui/tool_panels/___tool_panels.md)
- [Setup (folder)](setup/___setup.md) — the build pipeline: version
  info, SVG→ICO, PyInstaller, signing, NSIS installer, and a
  fail-closed verify gate
- [Main (Entry Point)](__about/main.md) — usage, options, exit codes
- [Tests (folder)](tests/___tests.md) — the offline safety net

## Running

```bash
pip install -r requirements.txt

# the front door — no arguments opens the GUI
python main.py
```

In the window: **Add** one or more sheets to the queue, pick the
output folder, tick Gemini / ChatGPT (both = parallel; each has its
own background dropdown — ChatGPT defaults to transparent, Gemini
to white and always gets its three forced laws: the aspect ratio
picked per prompt (badges 1:1, TALL lancets portrait), the
background, no reflections). Press **Open Chrome (login)** the
first time (the
dedicated `chrome-profile/` keeps you logged in from then on),
**Check sheets**, then **Start** — and go ride a bike.

Each site works through the queue in order, closing collection
after collection. The out/ tree MIRRORS DOMY's `assets/` — sheets
carry full site-agnostic `assets/...` paths and the tool injects
the site after the category (`out/emblem/gemini/mood/Glory.png`),
so a finished collection copies straight into `assets/`. Progress
sidecars and `<collection>_report.txt` (timestamps, per-image AI +
our times, resolutions, sizes, REMOVE BG actions, averages,
totals) live under `out/_state/<site>/`. The **Dashboard** tab shows the same numbers live —
per theme and for the whole task — with a collapsible history of
finished themes. A quota stop ends only that site's queue with
everything finished already saved — the next Start resumes the
rest. Every saved image goes through the in-house background
remover (transparent → kept, white → cleared + cropped, ambiguous
→ reported). A SAFETY refusal skips just that image; with **safer
retry** on, the item is re-sent once with an allegory-framing note
first.

CLI alternative (one site per run):

```bash
python main.py sheet1.md sheet2.md --site gemini
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --dry-run
```
