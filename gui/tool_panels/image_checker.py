"""``ImageCheckerSettingsPanel`` — the AI image checker's own settings
panel (GUI rework Phase 15): the SAME input-picker + Filter +
Start/Pause/Stop chrome every standalone tool has, plus its own
instructions box, the optional prompt-sheet source (F6) and the
model/pacing note.

Split out of the single-file ``gui/tool_panels.py`` (root Rule #20,
2026-07-30).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from painter.config import AI_CALL_PAUSE_S, STATE_DIRNAME
from ..model_picker import ModelPickerRow
from ..widgets import rounded_button
from .base import ToolSettingsPanel
from .layout import DENSE_COL_WRAP_PX


class ImageCheckerSettingsPanel(ToolSettingsPanel):
    """The AI image checker's persistent settings panel (GUI rework
    Phase 15) — the SAME input-picker + Filter + Start/Pause/Stop
    chrome every standalone tool now has, replacing the Main Menu/
    IconBar's old direct ``_start_ai_check`` launch (its own
    ``askdirectory`` + confirm ``askyesno``, both retired: the panel's
    OWN picker covers the folder/files, and Start — deliberately
    configured then clicked — already IS the confirmation, same
    contract as every sibling panel; see ``ToolSettingsPanel``'s own
    docstring and ``AspectSettingsPanel``'s "no confirm dialog here").

    No Advanced section (``HAS_ADVANCED = False``) — the checker has
    no engine knobs to hide, only the base's own input picker plus an
    OPTIONAL embedded ``FilterEditor`` (unseeded — empty means check
    EVERY image under the folder, same "empty = all" contract BG/Crop
    already use) and a short informational footer carrying what the
    old confirm dialog used to say (model + pacing + where flags
    persist), so the owner still sees that information without a
    blocking dialog.

    Its Start does NOT go through ``build_func``/``PainterGui.
    _start_tool_from_panel``/``_launch_tool_worker`` at all — the
    checker's own worker (``_run_ai_check_job``) has a fundamentally
    different shape from the four tools' shared ``_run_tool_job`` (no
    JobTemp backup — the run is read-only — no per-file engine
    callable, its own event types), so it is wired straight to
    ``PainterGui._start_ai_check`` instead (see that method's own
    docstring for the full flow). **Stop reuses ``PainterGui.
    _stop_tool`` UNCHANGED** — that method never touches
    ``_tool_panels`` and is already fully generic over any slot with a
    ``_tool_workers``/``_stop_events`` entry (it only sets the stop
    event, clears a pending pause and writes a status line), so a
    second near-identical ``_stop_ai_check`` method would only
    duplicate it byte-for-byte (Rule #5) — the constructor below wires
    ``on_stop=PainterGui._stop_tool`` exactly like BG/Crop/Upscale/
    Aspect.

    One asymmetry from its three siblings: this panel's MENU_TILES id
    ("image_checker") differs from its own ``SLOT``/JOB_ORDER kind
    ("aicheck") — the checker already existed as the dashboard's
    seventh job kind (``AiCheckPanel``, owner 2026-07-20) before this
    panel did, so its slot name predates and is independent of the
    tile system Phase 10 introduced. ``PainterGui._tool_panel_key``
    (backed by ``config.tile_for_kind``) is the one translation point
    that bridges the two spaces wherever `_toggle_pause_job`/
    `_dispatch` need to reach THIS panel from the "aicheck" kind.

    F6 (REWORK.md, owner E2): a SECOND, OPTIONAL picker
    (``_build_extra``) — a prompt-sheet ``.md`` FILE or a FOLDER of
    them, mirroring the Collections queue's own Add…/Add folder… pair
    (``config.iter_md_files`` backs the folder case). Empty (the
    default, ``sheets_path() -> None``) keeps today's images-only,
    quality-only behavior. When given, ``PainterGui._run_ai_check_job``
    pairs each checked image to its own sheet PROMPT via
    ``ai.drop_and_site_for`` (the ``dest_for`` reverse) and checks ONLY
    the matched subset — the picked path itself is handed over
    UNRESOLVED (a folder is only walked on the worker thread, never
    here on the Tk one)."""

    SLOT = "aicheck"
    HAS_ADVANCED = False

    def _picker_title_suffix(self) -> str:
        return "(read-only)"

    def _build_extra(self, box: ttk.Frame) -> None:
        # the VISION model pick lives HERE now (faza 4, owner UV
        # tačka 5: "podešavanje za IMAGE CHECK tamo ko to KORISTI" —
        # moved out of the API panel): the shared ModelPickerRow —
        # capable-only list, curated hint, immediate persist; the run
        # itself still resolves via ai.model_for("vision"), which
        # reads the SAME override this row writes.
        ttk.Label(
            box, text="Vision model (the checker's eyes)",
            style="Head.TLabel",
        ).pack(anchor="w", pady=(0, 2))
        self.model_picker = ModelPickerRow(box, "vision", "Vision")
        self.model_picker.pack(fill="x", pady=(0, 6))

        self._sheets_path: Path | None = None
        ttk.Label(
            box,
            text="Prompt sheets (optional) — pairs each MATCHED image"
            " with its own prompt for a content-match check:",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        rounded_button(
            row, "Sheet file…", command=self._pick_sheets_file,
            kind="info", width=110,
        ).pack(side="left")
        rounded_button(
            row, "Sheets folder…", command=self._pick_sheets_folder,
            kind="info", width=110,
        ).pack(side="left", padx=(6, 0))
        self._sheets_var = tk.StringVar(
            value="(none — every image gets a quality-only check)"
        )
        ttk.Label(
            box, textvariable=self._sheets_var, style="Muted.TLabel",
            wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w", pady=(4, 0))

    def _pick_sheets_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Prompt sheet (.md) — pairs a prompt with each"
            " matched image",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        self._sheets_path = Path(path)
        self._sheets_var.set(f"Sheet: {self._sheets_path}")

    def _pick_sheets_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Folder of prompt sheets (.md) — pairs a prompt with"
            " each matched image",
        )
        if not folder:
            return
        self._sheets_path = Path(folder)
        self._sheets_var.set(f"Sheets folder: {self._sheets_path}")

    def sheets_path(self) -> Path | None:
        """The picked prompt-sheet FILE or FOLDER (F6, owner E2) —
        ``None`` when nothing was picked (today's images-only, quality-
        only behavior). ``PainterGui._start_ai_check`` reads this
        alongside ``resolve_input()``/``get_conditions()`` and hands it
        to ``_run_ai_check_job`` unresolved."""
        return self._sheets_path

    def _build_footer(self, box: ttk.Frame) -> None:
        ttk.Label(
            box,
            text="Each image goes to the picked Vision model above for"
            " banal defects only (plus the prompt-match when sheets"
            f" are given), paced ~{AI_CALL_PAUSE_S:.0f}s per call on"
            " the free tier. Read-only — nothing is modified; flags"
            f" persist under the output folder's {STATE_DIRNAME}/.",
            style="Muted.TLabel", wraplength=DENSE_COL_WRAP_PX,
        ).pack(anchor="w")
