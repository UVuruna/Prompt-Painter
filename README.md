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
[PLAN.md](PLAN.md)** (the design discussion behind it). First
consumer: DOMY Watch prompt sheets.

## Structure

```
📁 PromptPainter/
  🐍 main.py            ← THE entry point (no args: GUI; sheets: CLI)
  📝 main.md
  🐍 gui.py             ← the tkinter window (main.py opens it)
  📝 gui.md
  ⚙️ requirements.txt   ← playwright, numpy/scipy/pillow, pytest
  📁 assets/
    🖼️ logo.svg
  📁 painter/           ← config, parser, driver, loop, chrome,
    📝 ___painter.md       bg remover, postprocess
    🐍 config.py
    🐍 sheet_parser.py
    🐍 driver.py
    🐍 runner.py
    🐍 chrome.py
    🐍 bg_remove.py
    🐍 postprocess.py
  📁 tests/             ← golden parser tests + offline loop tests
    📝 ___tests.md
    📁 fixtures/
  📁 out/               ← images + progress + reports (gitignored)
  📁 chrome-profile/    ← the automation Chrome profile (gitignored)
  📁 UV/                ← the owner's private material (gitignored)
```

## Documentation

- [Sheet-authoring instructions](instructions.md) — the contract a
  sheet author (person or agent) follows; also behind the GUI's
  **Instructions** button
- [Painter (folder)](painter/___painter.md) — the engine package:
  [Config](painter/config.md), [Sheet Parser](painter/sheet_parser.md),
  [CDP Driver](painter/driver.md), [Run Loop](painter/runner.md),
  [Chrome Launcher](painter/chrome.md),
  [Background Remover](painter/bg_remove.md),
  [Postprocess](painter/postprocess.md)
- [GUI](gui.md) — the window, the sheet queue, the threading
- [Main (Entry Point)](main.md) — usage, options, exit codes
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

Each site works through the queue in order, closing theme after
theme: images at `<out>/<site>/<drop-path>`, progress sidecar and
`<theme>_report.txt` (timestamps, per-image generate + process
times, resolutions, sizes, REMOVE BG actions, averages, totals)
beside them. The **Dashboard** tab shows the same numbers live —
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
