"""Screenshot the FIVE-column dashboard tree with real rows in it.

THE SPACE & LEGIBILITY LAW's visual proof for the 2026-08-11 column
rework (owner): the automatic audit renders every window EMPTY, and an
empty tree cannot show what this change was about — the merged Time
column, the delivered-only Res, Name taking the free space, and the
sixth "checked" badge dot. So this fills a DashPanel with a realistic
collection > folder > image tree and captures it.

Not a test — a proof generator, run by hand:

    python tests/shot_dash_columns.py

It writes .claude/shots/dash-columns/DashPanel_columns.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tests.test_layout_audit_tk import capture, settle  # noqa: E402

SHOT_DIR = PROJECT / ".claude" / "shots" / "dash-columns"

# one realistic collection: two folders, four images, one refusal —
# long enough drop paths to prove Name is no longer the cut column
ROWS = [
    ("assets/weeks/films/sw_jedi/primary/bronze/Padme_v2.png", 107.0, 29.0,
     "1254x1254", "1254x1246", 3_145_728, "REMOVE BG: done, CROP: done",
     True, "ok"),
    ("assets/weeks/films/sw_jedi/primary/bronze/ObiWan.png", 96.0, 18.0,
     "1024x1024", "1024x1024", 2_097_152, "REMOVE BG: done", False,
     "flagged"),
    ("assets/weeks/films/sw_sith/primary/colored/Grievous_v2.png", 122.0,
     13.0, "1536x1024", "1108x1024", 2_097_152,
     "REMOVE BG: done, UPSCALE: done", False, "ok"),
    ("assets/weeks/films/sw_sith/primary/colored/Dooku.png", 88.0, 24.0,
     "1024x1024", "932x931", 1_153_434, "CROP: done, ASPECT: done", False,
     "error"),
]


def build(app):
    """Fill the real app's ChatGPT DashPanel — the whole PainterGui is
    built (never a bare DashPanel on a naked root) so the capture shows
    the app's OWN theme, fonts and grid, exactly like the audit does."""
    panel = app.panels["chatgpt"]
    app._dashgrid.add("chatgpt")
    panel.begin_run(task_total=357, task_themes=23)
    panel.handle({
        "type": "sheet_start",
        "sheet": "starwars_descriptive_prompts.md", "pending": 38,
    })
    for drop, gen, over, orig, final, size, actions, retried, check in ROWS:
        panel.handle({
            "type": "item_progress", "idx": 1, "of": 38, "title": drop,
            "drop_path": drop, "rel": drop, "gen_s": gen,
            "orig_res": orig, "final_res": final, "size": size,
            "actions": actions, "retried": retried,
        })
        panel.handle({
            "type": "item_done", "drop_path": drop,
            "gen_s": gen, "over_s": over,
        })
        panel.handle({
            "type": "item_checked", "drop_path": drop, "kind": check,
            "defects": ["frame slightly cut off"] if check == "flagged" else [],
            "raw": "quota" if check == "error" else "", "rel": drop,
            "time": 4.0,
        })
    panel.handle({
        "type": "item_refused",
        "drop_path": "assets/weeks/films/sw_sith/primary/colored/Maul.png",
        "reason": "copyright", "diagnosis": "",
    })
    return panel


def main() -> int:
    import ttkbootstrap as tb

    import gui

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    # the same root the audit fixture builds — the app's own theme
    root = tb.Window(themename="darkly")
    root.geometry("+9000+40")     # off the screen
    # ...and fully transparent, exactly as run_audit does: an off-screen
    # window that is merely hidden never gets a WM_PAINT, so PrintWindow
    # captures its ttk widgets BLANK; the layered (alpha) window keeps a
    # real DWM surface and renders in full.
    root.attributes("-alpha", 0.0)
    from gui import app_settings
    app_settings.save_settings = lambda *_a, **_kw: None  # never the real file
    app = gui.PainterGui(root)
    # the RUNNING view (Phase 11) is where the dashboard tab lives
    app._set_view("running")
    build(app)
    root.update_idletasks()
    root.update()
    settle(root, 1057, 760)
    path = capture(root, "DashPanel_columns")
    # capture() writes into the audit's own folder — move it to ours
    target = SHOT_DIR / "DashPanel_columns.png"
    path.replace(target)
    print(f"wrote {target}")
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
