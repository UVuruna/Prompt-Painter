# CLAUDE.md — PromptPainter

A supervised automation tool that GENERATES IMAGES from the owner's
prompt-sheet `.md` files by driving his ALREADY OPEN, already logged-in
Gemini/ChatGPT browser tab (CDP attach): paste a prompt, wait for the
generation to finish, capture the image, save it under the sheet's own
filename into the theme's folder. The sheets live in his other projects
(first consumer: Watch Academy `research/prompts/`) — this tool only
consumes them, never edits them.

This file inherits the monorepo constitution
([root CLAUDE.md](../../CLAUDE.md)) and may only ADD or TIGHTEN its rules —
never loosen them. Decisions, workflow detail and DOM protocol live in
`docs/` (below); this file stays under 6,000 bytes.

profiles: laptop-avg, pc-low
installable: yes

## Stack

- Language / runtime: Python 3.12 + `playwright` (CDP attach, no browser
  extension)
- GUI: Tkinter + ttkbootstrap + customtkinter widgets (`gui/`)
- Key libraries: `playwright` (site driving), Pillow/numpy/scipy
  (background removal, postprocess), Real-ESRGAN ncnn-vulkan binary
  (upscaling, auto-downloaded into `tools/`, gitignored)
- Data / storage: files only — `settings.json` (owner config, gitignored),
  `output/` (everything the program generates, gitignored)

## How to run

```
python main.py                    no args: GUI; sheet args: single-site CLI
python main.py sheet.md --site gemini --dry-run
```

## How to test

```
python -m pytest tests -q                 full suite
python tests/run_guards.py                guards, FULL (Stop hook)
python tests/run_guards.py --fast         guards, fast (PostToolUse hook)
python ../../rules/tools/uv.py shot --all screenshots, every window x profile
```

## Entry points

| Path | Role |
|------|------|
| `main.py` | process entry — GUI or single-site CLI |
| `painter/runner.py` | the run loop (parse -> submit -> await -> save) |
| `painter/driver.py` | the CDP DOM driver (turn-based protocol) |
| `gui/app.py` | `PainterGui`, the main window |
| `.claude/uv_windows.py` | window registry for `uv shot` |

## Project laws

- **THE PATH IN THE SHEET IS THE PATH** (owner decree 2026-08-14, binding):
  the tool appends only the generator's registered suffix to the sheet's
  own path — never strips or invents a folder. Guard:
  `tests/test_runner_paths_and_save.py::test_dest_for_keeps_the_sheets_path_exactly`.
  Full context: [docs/DECISIONS.md](docs/DECISIONS.md).
- **Generator Suffix Registry**: every image generator MUST be registered in
  `SITE_FILE_SUFFIX` (`painter/config/paths.py`) before it generates a
  single image — the one authority, no suffix hardcoded elsewhere.
- **Sources are READ ONLY** — the tool writes only under the chosen output
  folder, never the sheet's own folder.
- **Selectors fail LOUDLY, never guess** — one config block with fallbacks
  per site (`painter/config/sites.py`); a reskin is a loud DriverError, not
  a silent no-op.
- **DONE = the file exists on disk** at its output path — no sidecar state;
  a run is resumable for free and never overwrites an existing file.
- GUI work here is ALSO governed by Zubi v2 ([GUI Rules](../../rules/GUI.md#zubi-v2)).
  This project authored the Tk template (`tests/layout_checks_tk.py`,
  copied to `rules/templates/layout_checks_tk.py`): ALG-5 uniform siblings,
  ALG-6 radius tiers, ALG-7 empty band, run by `tests/test_layout_zubi_tk.py`.
  Documented gaps (grader checklist): ALG-2 contrast, ALG-3 hover, ALG-8
  live profile, ALG-9 taxonomy.
- RATCHET (files allowed over the structure wall, shrinking only — Rule #20
  round DONE 2026-07-30 for the three worst + the guard; these five are the
  next round's debt): `gui/app_jobs.py`, `painter/driver.py`,
  `gui/agent_panel.py` + five test modules (see `tests/test_structure_law.py`
  for the exact list) — a second god-file split session owes them.

## Enforcement

Guard tests run via `tests/run_guards.py`
([Code Rules](../../rules/CODE.md) → Enforcement): fast pass (every
Edit/Write) = structure law, config sections, the layout law's static
banned-API grep. Full pass (Stop, session end, only when the session
changed something) additionally runs docs coverage, doc links, the runtime
layout audit (`test_layout_audit_tk.py`), Zubi v2 (`test_layout_zubi_tk.py`,
only when a GUI file changed), the clone guard
(`tests/clone_ratchet.json`) and the rules-size guard.

## Docs

- `README.md` — what it is, the name story, the navigation chain root
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — every owner decree with its
  date: core mechanic, workflow, suffix registry, sheet contract layer,
  DOM protocol decisions, honesty notes, open items
- [`instructions.md`](instructions.md) — the sheet-authoring contract (also
  behind the GUI's Instructions button)
- [`PROTOCOL.html`](PROTOCOL.html) — the full per-item DOM conversation
  protocol, rendered (open in a browser)
- [`UI-SKETCH.md`](UI-SKETCH.md) — setup-screen layout reference,
  implemented + verified 2026-07-30, kept until the owner formally closes it
- [`docs/AUDIT-OOP-2026-08-18.md`](docs/AUDIT-OOP-2026-08-18.md) — one kind,
  one class + structure audit, one-off per `rules/history/
  one-kind-one-class.md`
- `docs/history/` — landed design documents (PLAN, REWORK) kept for their
  reasoning, superseded by DECISIONS.md
- Folder docs: `gui/___gui.md`, `painter/___painter.md`,
  `painter/config/___config.md`, `painter/ai/___ai.md`, `setup/___setup.md`,
  `tests/___tests.md` → each folder's own `__about/`, `__flow/`

## Open items

See [docs/DECISIONS.md](docs/DECISIONS.md) → Open items (H1 crash
mitigation, Gemini copyright marker gap, `no_empty_space` wording, the
god-file RATCHET debt, UI-SKETCH.md sign-off).
