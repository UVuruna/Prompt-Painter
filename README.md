# PromptPainter

A supervised image-generation runner: reads a prompt-sheet `.md`
(theme + titled prompts), drives the owner's logged-in Gemini and/or
ChatGPT tabs over CDP — both in parallel when asked — captures each
generated image straight from the DOM, runs the DOMY background fix
over it, and files it as `<out>/<site>/<drop-path>` — named by the
sheet, resumable, paced, sources strictly read-only.

**Status:** built (engine + GUI); awaiting the first supervised live
run. **The handover pack: [CLAUDE.md](CLAUDE.md)** (the BINDING spec
— decisions, workflow, DOM states, build order) **+
[PLAN.md](PLAN.md)** (the design discussion behind it). First
consumer: DOMY Watch prompt sheets.

## Structure

```
📁 PromptPainter/
  🐍 gui.py             ← the front door (tkinter)
  📝 gui.md
  🐍 main.py            ← single-site CLI
  📝 main.md
  ⚙️ requirements.txt   ← playwright (runtime), pytest (dev)
  📁 painter/           ← config, parser, driver, loop, chrome, bgfix
    📝 ___painter.md
    🐍 config.py
    🐍 sheet_parser.py
    🐍 driver.py
    🐍 runner.py
    🐍 chrome.py
    🐍 postprocess.py
  📁 tests/             ← golden parser tests + offline runner tests
    📝 ___tests.md
    📁 fixtures/
  📁 out/               ← generated images + run state (gitignored)
  📁 chrome-profile/    ← the automation Chrome profile (gitignored)
  📁 UV/                ← the owner's private material (gitignored)
```

## Documentation

- [Painter (folder)](painter/___painter.md) — the engine package:
  [Config](painter/config.md), [Sheet Parser](painter/sheet_parser.md),
  [CDP Driver](painter/driver.md), [Run Loop](painter/runner.md),
  [Chrome Launcher](painter/chrome.md), [Postprocess](painter/postprocess.md)
- [GUI](gui.md) — the window, the buttons, the threading
- [Main (CLI)](main.md) — usage, options, exit codes
- [Tests (folder)](tests/___tests.md) — the offline safety net

## Running

```bash
pip install -r requirements.txt

# the front door
python gui.py
```

In the window: pick the sheet and the output folder, tick Gemini /
ChatGPT (both = parallel), press **Open Chrome (login)** — the tool
launches its own automation Chrome (`chrome-profile/`; Chrome 136+
refuses CDP on the default profile, so you log in HERE once and
stay logged in) — then **Check sheet**, then **Start**, and watch
the windows.

CLI alternative (one site per run):

```bash
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --dry-run
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --site gemini
```

Runs are paced, per-site sequential, supervised and resumable —
progress lives in `<out>/<site>/<sheet-stem>.progress.json`, so a
crash or a quota stop costs nothing. ChatGPT prompts ask for a
TRANSPARENT background, Gemini prompts for flat WHITE; every saved
image then goes through DOMY Watch's `bg_remove.py` (transparent →
kept, white → cleared, ambiguous → reported). Quota/refusal
responses stop the run loudly; run again later to resume.
