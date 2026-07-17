# PromptPainter

<img src="assets/logo.svg" width="96" align="right">

A supervised image-generation runner: reads a prompt-sheet `.md`
(theme + titled prompts), drives the owner's logged-in Gemini and/or
ChatGPT tabs over CDP — both in parallel when asked — captures each
generated image straight from the DOM, clears its background, and
STAGES it for the owner's review; only approval files an image at
its final `<out>/<site>/<drop-path>`. Named by the sheet, resumable,
paced, sources strictly read-only.

**Status:** built (engine + GUI + review flow); awaiting the first
supervised live run.
**GitHub:** [UVuruna/Prompt-Painter](https://github.com/UVuruna/Prompt-Painter)
**The handover pack: [CLAUDE.md](CLAUDE.md)** (the BINDING spec —
decisions, workflow, DOM states, build order) **+
[PLAN.md](PLAN.md)** (the design discussion behind it). First
consumer: DOMY Watch prompt sheets.

## Structure

```
📁 PromptPainter/
  🐍 main.py            ← THE entry point (no args: GUI; sheet: CLI)
  📝 main.md
  🐍 gui.py             ← the tkinter window (main.py opens it)
  📝 gui.md
  ⚙️ requirements.txt   ← playwright, numpy/scipy/pillow, pytest
  📁 assets/
    🖼️ logo.svg
  📁 painter/           ← config, parser, driver, loop, chrome,
    📝 ___painter.md       bg remover, postprocess, review
    🐍 config.py
    🐍 sheet_parser.py
    🐍 driver.py
    🐍 runner.py
    🐍 chrome.py
    🐍 bg_remove.py
    🐍 postprocess.py
    🐍 review.py
  📁 tests/             ← golden parser tests + offline loop tests
    📝 ___tests.md
    📁 fixtures/
  📁 out/               ← _staging/ + approved images (gitignored)
  📁 chrome-profile/    ← the automation Chrome profile (gitignored)
  📁 UV/                ← the owner's private material (gitignored)
```

## Documentation

- [Painter (folder)](painter/___painter.md) — the engine package:
  [Config](painter/config.md), [Sheet Parser](painter/sheet_parser.md),
  [CDP Driver](painter/driver.md), [Run Loop](painter/runner.md),
  [Chrome Launcher](painter/chrome.md),
  [Background Remover](painter/bg_remove.md),
  [Postprocess](painter/postprocess.md), [Review](painter/review.md)
- [GUI](gui.md) — the window, the review flow, the threading
- [Main (CLI)](main.md) — usage, options, exit codes
- [Tests (folder)](tests/___tests.md) — the offline safety net

## Running

```bash
pip install -r requirements.txt

# the front door — no arguments opens the GUI
python main.py
```

In the window: pick the sheet and the output folder, tick Gemini /
ChatGPT (both = parallel), pick the background (`auto` = transparent
on ChatGPT, white on Gemini), press **Open Chrome (login)** — the
tool launches its own automation Chrome (`chrome-profile/`; Chrome
136+ refuses CDP on the default profile, so you log in HERE once
and stay logged in) — then **Check sheet**, then **Start**, and
watch the windows.

When the run ends, the **review window** opens: every image was
staged under `<out>/_staging/<site>/` — Approve moves it to
`<out>/<site>/<drop-path>`, Reject deletes it and the next run
regenerates it (rework the prompt in the sheet first).

CLI alternative (one site per run):

```bash
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --dry-run
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --site gemini --approve-all
```

Runs are paced, per-site sequential, supervised and resumable —
progress lives beside the staged images, so a crash or a quota stop
costs nothing. Every saved image goes through the in-house
background remover (transparent → kept, white → cleared + cropped,
ambiguous → reported). Quota/refusal responses stop the run loudly;
run again later to resume.
