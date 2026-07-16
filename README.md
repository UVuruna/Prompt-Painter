# PromptPainter

A supervised image-generation runner: reads a prompt-sheet `.md`
(theme + titled prompts), drives the owner's already open
Gemini/ChatGPT tab over CDP, captures each generated image straight
from the DOM and files it as `out/<theme>/<name>.png` — named by
the sheet, resumable, paced.

**Status:** in definition. **The handover pack: [CLAUDE.md](CLAUDE.md)**
(the BINDING spec — decisions, mechanics, DOM states, build order;
the new agent loads it automatically) **+ [PLAN.md](PLAN.md)** (the
design discussion behind it). First consumer: DOMY Watch prompt
sheets.

## Structure (planned)

```
📁 PromptPainter/
  🐍 main.py            ← entry point (sheet path + site flag)
  📁 painter/           ← sheet parser, CDP driver, run loop
  📁 tests/             ← golden parser tests over real sheets
  📁 out/               ← generated images per theme (gitignored)
```

## Running (planned)

```bash
pip install -r requirements.txt   # playwright
# Chrome once: chrome.exe --remote-debugging-port=9222
python main.py "path/to/theme_prompts.md" --site gemini
```
