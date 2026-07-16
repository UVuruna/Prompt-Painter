# PromptPainter

A supervised image-generation runner: reads a prompt-sheet `.md`
(theme + titled prompts), drives the owner's already open
Gemini/ChatGPT tab over CDP, captures each generated image straight
from the DOM and files it under the sheet's own drop path as
`out/<drop-path>` — named by the sheet, resumable, paced.

**Status:** built; awaiting the first supervised live run.
**The handover pack: [CLAUDE.md](CLAUDE.md)** (the BINDING spec —
decisions, mechanics, DOM states, build order) **+
[PLAN.md](PLAN.md)** (the design discussion behind it). First
consumer: DOMY Watch prompt sheets.

## Structure

```
📁 PromptPainter/
  🐍 main.py            ← entry point (sheet path + site flag)
  📝 main.md
  ⚙️ requirements.txt   ← playwright (runtime), pytest (dev)
  📁 painter/           ← config, sheet parser, CDP driver, run loop
    📝 ___painter.md
    🐍 config.py
    🐍 sheet_parser.py
    🐍 driver.py
    🐍 runner.py
  📁 tests/             ← golden parser tests over the real sheets
    📝 ___tests.md
    📁 fixtures/
  📁 out/               ← generated images + run state (gitignored)
```

## Documentation

- [Painter (folder)](painter/___painter.md) — the engine package:
  [Config](painter/config.md), [Sheet Parser](painter/sheet_parser.md),
  [CDP Driver](painter/driver.md), [Run Loop](painter/runner.md)
- [Main (CLI)](main.md) — usage, options, exit codes
- [Tests (folder)](tests/___tests.md) — the golden tests

## Running

```bash
pip install -r requirements.txt

# validate a sheet offline (no browser needed)
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --dry-run

# Chrome once, with the owner's real profile:
#   chrome.exe --remote-debugging-port=9222
# then the supervised run (watch the window):
python main.py "..\DOMY Watch\research\prompts\archetype\trinity_prompts.md" --site gemini
```

Runs are paced (configurable pause between prompts), single-window,
supervised, and resumable — progress lives in
`out/<sheet-stem>.progress.json`, so a crash or a quota stop costs
nothing. Quota/refusal responses stop the run loudly; rerun later to
resume.
