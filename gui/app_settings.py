"""SettingsMixin — the queue/sheet helpers, prerequisite handlers, AI
features gate, and settings persistence.

Godfile refactor step 7/8 (see gui/___gui.md): the sixth of PainterGui's
six mixins (see gui/app.py — a sixth, CheckerFixerMixin, split out of
SiteJobsMixin in step 8/8). Owns the Collections queue (Add…/Add
folder…/Remove/Clear — ``_queue_sheets``/``_add_sheets``/
``_add_sheets_folder``/``_remove_sheet``/``_clear_sheets``), the sheet
parsing/planning helpers shared by the site jobs (``_parse_all``/
``_out_base``/``_done_on_disk``/``_plan``), the dashboard row viewers
(``_show_node``/``_show_folder_excerpt``), the top-strip "prerequisite"
button handlers (``_check_sheets``/``_select_images``/
``_open_instructions``/``_new_collection_ai``/``_open_key_wizard`` —
``_open_chrome`` was retired in F4g: Chrome is ensured at Start), the
AI-features key gate (``gemini_key``/``set_gemini_key``/
``_ensure_ai_key``/``add_generated_sheet``) and the whole settings
round-trip (``_collect_settings``/``_apply_settings``/the two one-time
migration helpers/``_schedule_save``/``_save_now``/``_on_close``). No
``__init__`` here — every attribute it reads is set by
``BuildMixin.__init__``.

Two of ``DocWindow``'s call sites here go through a deferred
``import gui`` (the SAME late-binding idiom already used in
gui/dash_panels.py, gui/viewers.py, gui/tool_dash.py and
gui/api_panel.py) so that tests/test_gui_checker.py's and
tests/test_gui_fixer.py's ``monkeypatch.setattr(gui, "DocWindow", ...)``
reaches the class actually constructed here, instead of a module-level
copy frozen at import time.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import datetime
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox

from painter import config, jobtemp
from painter.config import (
    DEFAULT_OUT_DIR,
    FILTER_PRESETS_SETTING,
    GEMINI_KEY_SETTING,
    JOBTEMP_STEP_LABEL,
    SITES,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_SIDE_DEFAULT,
    dest_for,
    iter_md_files,
)
from painter.settings import save_settings
from painter.sheet_parser import Sheet, SheetError, parse_sheet
from . import widgets
from .dialogs import AiKeyWizard
from .logic import (
    _migrate_legacy_aspect_filter,
    _migrate_legacy_upscale_gate,
    _parse_condition_dicts,
)
from .select_window import SelectWindow
from .image_viewer import ImageViewer
from .restore_windows import _filmstrip_stages
from .viewer_shared import _restore_step
from .widgets import folder_of

# GUI rework Phase F4f: the reverse of JOBTEMP_STEP_LABEL — ImageViewer's
# Steps section only ever hands back a friendly LABEL (never the raw
# JobTemp step key, see ImageViewer's own docstring for why), so the
# 'Restore to this step' wiring built in _image_viewer_restore_cb below
# maps it back before calling JobTemp.restore_to. Built once here (not
# per-call) since JOBTEMP_STEP_LABEL is fixed config data with unique
# values.
_STEP_LABEL_TO_KEY = {label: step for step, label in JOBTEMP_STEP_LABEL.items()}


class SettingsMixin:
    """Queue/sheet management, prerequisite top-strip actions, the AI
    features key gate, and settings persistence."""

    def _open_instructions(self) -> None:
        path = config.PROJECT_ROOT / "instructions.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("PromptPainter", f"Cannot read {path}: {exc}")
            return
        # deferred import (see module docstring) — reaches the class
        # tests monkeypatch through the gui package object
        import gui
        gui.DocWindow(
            self.root, "How to write a prompt sheet", text,
            hint="Give this to whoever (a person or an AI) writes the"
            " next prompt file.",
        )

    def _show_node(self, site_key: str, info: dict) -> None:
        """A dashboard row's 'Show': a collection opens its whole file,
        a FOLDER opens only that folder's excerpt of the sheet, an
        IMAGE opens ``ImageViewer`` (GUI rework Phase F4f, owner G6/G7)
        over the WHOLE collection's items so Prev/Next can walk it in
        one window — ``DocWindow`` stays for the collection/folder
        levels, unchanged.

        F4h (owner 2026-07-29, the unreproduced folder-view crash):
        the whole open is GUARDED — a viewer failure logs the full
        traceback and shows a dialog instead of killing the app, so a
        recurrence pins itself (REWORK.md open items; instrumented,
        NOT declared fixed)."""
        try:
            self._show_node_inner(site_key, info)
        except Exception as exc:  # loud, never app-fatal
            import traceback

            self._log(
                f"VIEWER ERROR ({info.get('level')}):"
                f" {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            )
            messagebox.showerror(
                "PromptPainter",
                f"The viewer failed to open: {exc}\n\n(The full error"
                " is in the Log tab — please report it.)",
            )

    def _show_node_inner(self, site_key: str, info: dict) -> None:
        source = next(
            (p for p in self._sheets if p.name == info["sheet"]), None
        )
        if source is None:
            messagebox.showinfo(
                "PromptPainter",
                f"{info['sheet']} is no longer in the queue.",
            )
            return
        # deferred import (see module docstring) — reaches the class
        # tests monkeypatch through the gui package object
        import gui
        if info["level"] == "image":
            try:
                sheet = parse_sheet(source)
            except (SheetError, OSError) as exc:
                messagebox.showerror("PromptPainter", str(exc))
                return
            entries, start = self._image_viewer_entries(site_key, sheet, info)
            if not entries:
                messagebox.showinfo(
                    "PromptPainter",
                    f"No prompt found for {info['drop']} in {source.name}.",
                )
                return
            panel = getattr(self, "panels", {}).get(site_key)
            ImageViewer(
                self.root, entries, start,
                check_lookup=self._image_viewer_check_lookup(panel),
                steps_lookup=self._image_viewer_steps_lookup(panel),
                restore_cb=self._image_viewer_restore_cb(panel),
                on_restored=partial(self._image_viewer_on_restored, panel),
                on_deleted=self._image_viewer_on_deleted,
            )
        elif info["level"] == "folder":
            self._show_folder_excerpt(source, info["folder"])
        else:
            try:
                text = source.read_text(encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("PromptPainter", str(exc))
                return
            gui.DocWindow(self.root, source.name, text)

    # --- ImageViewer wiring (GUI rework Phase F4f, owner G6/G7) --------

    def _image_viewer_entries(
        self, site_key: str, sheet: Sheet, info: dict,
    ) -> tuple[list[dict], int]:
        """The ORDERED entries ``ImageViewer`` walks for the CLICKED
        image's whole collection: every item of ``sheet``, in sheet
        order, dest resolved via ``dest_for`` + this run's out base —
        except the CLICKED item itself, whose ``rel`` comes from the
        dashboard row's own node info when present (the ACTUAL saved
        file, which may be a redo's ``_vN`` sibling — see REWORK.md's
        Run Loop; every OTHER item in the list uses the plain canonical
        ``dest_for``, same simplification the old single-image 'Show'
        already made). A refused item shows its ACTUAL refusal message
        + the site's own diagnostic answer (owner 2026-08-11) — the
        ``item_refused`` event's reason/diagnosis kept by
        ``DashPanel._refused_info``; items with no stored refusal fall
        back to the generic note rather than a fabricated specific
        reason."""
        out_base = self._out_base()
        panel = getattr(self, "panels", {}).get(site_key)
        refused_info = (
            getattr(panel, "_refused_info", {}) if panel is not None else {}
        )
        clicked_drop = info.get("drop")
        entries: list[dict] = []
        start = 0
        for i, item in enumerate(sheet.items):
            if item.drop_path == clicked_drop and info.get("rel"):
                rel = info["rel"]
            else:
                rel = dest_for(item.drop_path, site_key)
            dest = out_base / rel
            exists = dest.is_file()
            reason = None
            if not exists:
                stored = refused_info.get(item.drop_path)
                if stored:
                    reason = f"REFUSED — {stored['reason']}"
                    if stored.get("diagnosis"):
                        reason += (
                            "\n\nWHY (site's own answer):\n"
                            f"{stored['diagnosis']}"
                        )
                else:
                    reason = (
                        "No saved file — refused, skipped, or not"
                        " generated yet."
                    )
            entries.append({
                "title": item.title,
                "drop_path": item.drop_path,
                "rel": rel if exists else None,
                "dest": dest if exists else None,
                "prompt": item.prompt,
                "refused_reason": reason,
            })
            if item.drop_path == clicked_drop:
                start = i
        return entries, start

    def _image_viewer_check_lookup(self, panel):
        """``ImageViewer``'s ``check_lookup`` — the SAME
        ``DashPanel._check_results`` dict (keyed by drop path)
        ``_show_check`` already reads; None when not opened from a live
        dashboard panel (e.g. the panel slot never started a job)."""
        if panel is None:
            return None
        return panel._check_results.get

    def _image_viewer_steps_lookup(self, panel):
        """``ImageViewer``'s ``steps_lookup`` — the SAME
        ``_filmstrip_stages`` list ``StepRestoreWindow`` renders, minus
        its own trailing 'current' entry (ImageViewer's Steps section
        must be ABSENT when there are zero real backups, never present
        showing only 'current')."""
        if panel is None:
            return None

        def lookup(rel: str) -> list[tuple[str, Path]]:
            temp = panel.jobtemp
            if temp is None or not temp.steps_for(rel):
                return []
            live_path = (panel.out_base or self._out_base()) / rel
            return _filmstrip_stages(temp, rel, live_path)[:-1]

        return lookup

    def _image_viewer_restore_cb(self, panel):
        """``ImageViewer``'s ``restore_cb(rel, label) -> bool`` — maps
        the Steps section's display LABEL back to the raw JobTemp step
        key (``_STEP_LABEL_TO_KEY``) and calls the SAME ``_restore_step``
        helper ``StepRestoreWindow._do_restore`` calls (Rule #5)."""
        if panel is None:
            return None

        def restore(rel: str, label: str) -> bool:
            temp = panel.jobtemp
            step = _STEP_LABEL_TO_KEY.get(label)
            if temp is None or step is None:
                return False
            return _restore_step(temp, rel, step)

        return restore

    def _image_viewer_on_restored(self, panel, entry: dict) -> None:
        """After a Steps restore, refresh the dashboard row's
        resolution/size straight off disk — the SAME refresh
        ``DashPanel._show_steps``'s own ``on_restored`` already wires
        for ``StepRestoreWindow``."""
        if panel is not None and entry.get("drop_path"):
            panel.refresh_image_row(entry["drop_path"])

    def _image_viewer_on_deleted(self, entry: dict) -> None:
        """ImageViewer's Delete callback (owner G7). ``entry`` arrives
        ALREADY marked deleted (``ImageViewer._delete_current`` clears
        its own ``dest``/``rel`` before firing this, so the viewer's own
        Prev/Next immediately reflects it) — only ``drop_path``/
        ``title`` survive to identify WHICH image this was. The
        dashboard row is NOT cheaply reachable from here — no rel/drop
        -> tree-node index survives a collection switch
        (``DashPanel._child_ids`` is reset per collection, see its own
        comment in ``_new_theme``) — so this just logs; the row itself
        stays showing its last-known state until the run naturally
        re-reads the file (a rerun/redo) or the owner reopens Show.
        Building the machinery to hunt down and live-patch an arbitrary
        past row would be new cross-module plumbing for a cosmetic gap,
        not a fix (root Rule #15)."""
        self._log(f"DELETED image — {entry.get('drop_path', '?')}")

    def _show_folder_excerpt(self, source: Path, folder: str) -> None:
        """Only the contiguous portion of the sheet covering the
        entries whose drop paths live in ``folder`` — from the first
        such entry's heading line through the last one's prompt
        fence."""
        try:
            sheet = parse_sheet(source)
            lines = source.read_text(encoding="utf-8").splitlines()
        except (SheetError, OSError) as exc:
            messagebox.showerror("PromptPainter", str(exc))
            return
        members = [
            it for it in sheet.items
            if folder_of(it.drop_path) == folder
        ]
        if not members:
            messagebox.showinfo(
                "PromptPainter",
                f"No entries of {folder} found in {source.name}.",
            )
            return
        start = min(it.line for it in members) - 1  # entry line, 0-based
        # the excerpt ends at the closing fence of the LAST member's
        # prompt: scan from its heading for the opening ``` then the
        # closing one
        last = max(it.line for it in members) - 1
        end = len(lines) - 1
        fences = 0
        for i in range(last, len(lines)):
            if lines[i].lstrip().startswith("```"):
                fences += 1
                if fences == 2:
                    end = i
                    break
        excerpt = "\n".join(
            [f"# {sheet.theme} — {folder}", ""] + lines[start:end + 1]
        )
        # deferred import (see module docstring) — reaches the class
        # tests monkeypatch through the gui package object
        import gui
        gui.DocWindow(
            self.root, folder, excerpt,
            hint=f"Only this folder's part of {source.name}.",
        )

    # --- helpers -------------------------------------------------------

    def _log(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {line}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _queue_sheets(self, paths) -> None:
        """Append PATHS to the collection queue, de-duplicated by path —
        the shared body behind Add… and Add folder… (also reused by the
        AI sheet generator's own queue-one-sheet call)."""
        for raw in paths:
            path = Path(raw)
            if path not in self._sheets:
                self._sheets.append(path)
        self._repaint_sheet_lists()
        self._schedule_save()
        self._refresh_prompt_image()

    def _add_sheets(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Prompt sheets", filetypes=[("Markdown", "*.md")]
        )
        self._queue_sheets(paths)

    def _add_sheets_folder(self) -> None:
        """'Add folder…' — every ``.md`` sheet under a chosen folder,
        however nested, queued in one go (recursive, same de-dup rule
        as Add…)."""
        folder = filedialog.askdirectory(
            title="Folder with prompt sheets (.md)"
        )
        if not folder:
            return
        self._queue_sheets(iter_md_files(folder))

    def _remove_sheet(self, listbox=None) -> None:
        """Remove the selection of ONE column's queue view (faza 3:
        each CollectionsColumn's Remove passes its OWN listbox — its
        selection is the intent; ``None`` keeps the primary website
        column, the pre-faza-3 call shape)."""
        box = listbox if listbox is not None else self.sheet_list
        for index in reversed(box.curselection()):
            del self._sheets[index]
        self._repaint_sheet_lists()
        self._schedule_save()
        self._refresh_prompt_image()

    def _clear_sheets(self) -> None:
        self._sheets.clear()
        self._repaint_sheet_lists()
        self._schedule_save()
        self._refresh_prompt_image()

    def _repaint_sheet_lists(self) -> None:
        """Refill EVERY registered CollectionsColumn's queue view from
        the one ``self._sheets`` truth (faza 3 — the website setup and
        the API panel each render the same queue)."""
        for column in self._collections_columns:
            column.repaint_queue(self._sheets)

    def _refresh_prompt_image(self) -> None:
        """Keep the Prompt+Image eligibility views live across queue
        mutations (faza 2/3, every column) — a no-op while the mode is
        off (a hidden section re-parses on its next reveal anyway)."""
        if self._pi_section.enabled():
            for column in self._collections_columns:
                column.pi_section.refresh()

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="Output folder")
        if path:
            self.out_var.set(path)

    def _out_base(self) -> Path:
        return Path(
            self.out_var.get().strip() or str(DEFAULT_OUT_DIR)
        ).resolve()

    def _done_on_disk(self, site: str, sheet: Sheet) -> set:
        """Drop paths whose saved FILE already exists for one
        site+collection — the SAME dest the runner writes to
        (``out_base / dest_for``). "Done" means the image is really on
        disk (owner 2026-07-19), not merely recorded in a sidecar: a
        done item can be re-ticked to regenerate, and an item only
        recorded elsewhere never falsely reads as done."""
        out_base = self._out_base()
        return {
            item.drop_path
            for item in sheet.items
            if (out_base / dest_for(item.drop_path, site)).exists()
        }

    def _parse_all(self) -> list[Sheet]:
        """Parse every queued sheet; broken ones are reported and
        dropped from the run (the fix belongs in the sheet)."""
        good: list[Sheet] = []
        for path in self._sheets:
            try:
                sheet = parse_sheet(path)
            except (SheetError, OSError) as exc:
                self._log(f"SHEET SKIPPED: {exc}")
                continue
            if sheet.problems:
                for pr in sheet.problems:
                    self._log(
                        f"  PROBLEM {path.name} L{pr.line}: {pr.message}"
                    )
                self._log(
                    f"SHEET SKIPPED (contract problems): {path.name} —"
                    " fix the sheet and rerun"
                )
                continue
            self._log(
                f"OK {path.name}: {sheet.theme} —"
                f" {len(sheet.items)} to generate,"
                f" {len(sheet.skipped)} skipped"
            )
            for it in sheet.items:
                if it.advice:
                    self._log(
                        f"    ADVICE (unticked by default, L{it.line})"
                        f" {it.title} — {it.advice}"
                    )
            for sk in sheet.skipped:
                self._log(
                    f"    NO PROMPT in the sheet (L{sk.line})"
                    f" {sk.title} — {sk.reason}"
                )
            good.append(sheet)
        return good

    def _plan(
        self,
        site: str,
        sheets: list[Sheet],
        selection: dict[str, set[str] | None],
    ) -> tuple[int, int]:
        """Mirror run_sheet's queue rule to pre-count this run's scope:
        (total images to generate, number of themes with work). A
        ticked selection generates EXACTLY those items (regenerate
        included — file existence ignored); with no selection the
        runner resumes by FILE EXISTENCE and sits advice out."""
        total = 0
        themes = 0
        for sheet in sheets:
            sel = selection.get(str(sheet.source))
            if sel is not None:
                pending = [it for it in sheet.items if it.drop_path in sel]
            else:
                done = self._done_on_disk(site, sheet)
                pending = [
                    it for it in sheet.items
                    if it.drop_path not in done and not it.advice
                ]
            if pending:
                total += len(pending)
                themes += 1
        return total, themes

    # --- actions -------------------------------------------------------
    # F4g (owner 2026-07-29): the old _open_chrome handler (and its
    # top-strip button) is GONE — starting an agent ensures Chrome
    # itself: launch with the automation profile, open the site tab,
    # wait for the owner's login (see SiteJobsMixin._drive_site and
    # SiteDriver.wait_for_login).

    def _check_sheets(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        # show the output happening — Check reports into the log
        self.notebook.select(self._log_tab)
        self._parse_all()

    def _select_var(
        self, site: str, source: str, drop: str, default: bool = True
    ) -> tk.BooleanVar:
        key = (site, source, drop)
        if key not in self._select_vars:
            self._select_vars[key] = tk.BooleanVar(value=default)
        return self._select_vars[key]

    def _select_images(self) -> None:
        if not self._sheets:
            messagebox.showerror("PromptPainter", "Add sheet .md files first.")
            return
        sheets = self._parse_all()
        if not sheets:
            messagebox.showerror(
                "PromptPainter", "No usable sheets in the queue."
            )
            return
        # F4d (owner 2026-07-29): only the TICKED sites' columns show
        ticked = [
            key for key, panel in self.agents.items()
            if panel.visible_var.get()
        ]
        SelectWindow(self, sheets, site_keys=ticked or None)

    # --- the in-place tools (each its own concurrent job + panel) ------

    def _on_filter_presets_changed(self) -> None:
        """A FilterEditor mutates ``self._filter_presets`` (the shared
        dict reference passed at construction) IN PLACE on Save/Delete
        — this just schedules the debounced settings save (the same
        ``_schedule_save`` every other remembered choice already uses)
        so the change survives the next autosave/close instead of
        being silently dropped by ``_collect_settings``'s next
        full-file rewrite (settings.json is always a full overwrite,
        never a merge — see ``_save_now``)."""
        self._schedule_save()

    @property
    def gemini_key(self) -> str:
        return self._gemini_key

    def set_gemini_key(self, key: str) -> None:
        """The wizard's Save: remember + persist IMMEDIATELY (painter.ai
        reads the key back from settings.json on every call, so the
        debounced save would race a feature started right after)."""
        self._gemini_key = key
        self._save_now()
        self._log("Gemini API key saved to settings.json")

    def _open_key_wizard(self) -> None:
        AiKeyWizard(self.root, self)

    def _ensure_ai_key(self) -> bool:
        """True when a key is on disk. On ``NoKey`` the guided wizard
        opens AUTOMATICALLY (the spec'd auto-open) and the key is
        re-checked once it closes."""
        from painter import ai

        try:
            ai.api_key()
            return True
        except ai.NoKey:
            self._log("AI: no Gemini API key — opening the guided wizard")
            AiKeyWizard(self.root, self)
        try:
            ai.api_key()
            return True
        except ai.NoKey:
            self._log("AI: still no key — cancelled")
            return False

    def _new_collection_ai(self) -> None:
        """'New collection (AI)…' — the wizard is a REAL setup panel
        now (faza 4, owner UV tačka 4: ``SheetGenPanel``,
        ``_tool_panels["ai_sheet_gen"]``); the key gate moved onto its
        own Ask-questions action, so opening the panel is free."""
        self._open_tool_panel("ai_sheet_gen")

    def add_generated_sheet(self, path: Path) -> None:
        """Queue one AI-generated sheet (the same de-dup rule as Add…)."""
        self._queue_sheets([path])

    def _collect_settings(self) -> dict:
        return {
            "output": self.out_var.get(),
            "font_base": widgets.FONT_BASE,
            "theme": widgets.ACTIVE_THEME,
            "geometry": self.root.geometry(),
            "controls_collapsed": self._collapsed,
            # F4e (owner 2026-07-29): the dashboard grid/slider mode
            "dash_mode": self._dashgrid.mode,
            # the AI features' credential (owner 2026-07-20): held on
            # the GUI so the whole-dict save round-trips it; painter.ai
            # reads it back from settings.json per call
            GEMINI_KEY_SETTING: self._gemini_key,
            # F2 (owner 2026-07-29): persisted per-site quota reset
            # moments (unix epoch) — INFO only, expired entries dropped
            "site_cooldowns": {
                key: until
                for key, until in self._cooldowns.items()
                if until > time.time()
            },
            FILTER_PRESETS_SETTING: {
                name: list(rows) for name, rows in self._filter_presets.items()
            },
            "agents": {
                key: panel.get_settings()
                for key, panel in self.agents.items()
            },
            # PROMPT + IMAGE mode (faza 2, owner 2026-08-03): the
            # toggle + the Reference folder, same round-trip shape as
            # every panel above
            "prompt_image": self._pi_section.get_settings(),
            # GUI rework Phase 13/14: each standalone tool's PERSISTENT
            # settings panel (all four now) — its filter stack + Advanced
            # (or always-visible, for upscale/aspect) overrides, same
            # round-trip shape as "agents" above. The picked folder/files
            # are NEVER persisted (every tool has always asked fresh).
            # SUPERSEDES the old top-level 'upscale_tool'/'aspect_ratio'/
            # 'aspect_filter_conditions' keys the standalone Upscale/
            # Aspect MODAL dialogs used to own (both retired this phase)
            # — those old keys are simply no longer emitted here (see
            # _apply_settings's one-time migration INTO this dict below,
            # same "additive, read-old-once, log loudly" contract as
            # every other settings migration in this file).
            "tool_panels": {
                slot: panel.get_settings()
                for slot, panel in self._tool_panels.items()
            },
        }

    def _migrate_upscale_panel_settings(
        self, panel_stored: dict, stored: dict
    ) -> dict:
        """One-time migration (GUI rework Phase 14, same additive/
        read-old-once/log-loudly contract as every other settings
        migration in this file) of the retired standalone Upscale
        dialog's remembered gate — settings.json's old top-level
        ``upscale_tool`` key, EITHER the Phase 6+ ``{"min_side",
        "conditions"}`` shape or the pre-Phase-6 ``{"min_width",
        "min_height", "aspect_min", "aspect_max"}`` one — into
        ``UpscaleSettingsPanel``'s OWN settings shape (``up_minside``/
        ``conditions``, exactly what its ``get_settings``/
        ``apply_settings`` already read/write). A no-op once the panel
        has saved itself at least once under the NEW ``tool_panels``
        key (its own ``up_minside`` already present) — the old
        top-level key is never written back (``_collect_settings`` no
        longer emits it), so it naturally drops off disk over time,
        same as any other stale key."""
        if "up_minside" in panel_stored:
            return panel_stored
        saved_up = stored.get("upscale_tool")
        if isinstance(saved_up, dict) and "min_side" in saved_up:
            panel_stored = dict(panel_stored)
            panel_stored.setdefault("up_minside", str(saved_up["min_side"]))
            raw_conditions = saved_up.get("conditions")
            if isinstance(raw_conditions, list):
                panel_stored.setdefault("conditions", raw_conditions)
            self._log(
                "MIGRATION: standalone Upscale tool's remembered gate"
                " (top-level 'upscale_tool') -> the Upscale panel's own"
                " settings (one-time; the old key stays on disk unread"
                " from now on)"
            )
        elif isinstance(saved_up, dict) and "min_width" in saved_up:
            try:
                migrated = _migrate_legacy_upscale_gate(
                    saved_up.get("min_width", UPSCALE_MIN_SIDE_DEFAULT),
                    saved_up.get("aspect_min", UPSCALE_ASPECT_MIN),
                    saved_up.get("aspect_max", UPSCALE_ASPECT_MAX),
                )
            except (TypeError, ValueError) as exc:
                self._log(
                    f"MIGRATION: legacy 'upscale_tool' dict is unreadable"
                    f" ({exc}) — the Upscale panel keeps its shipped"
                    " default gate"
                )
            else:
                self._log(
                    "MIGRATION: legacy standalone 'upscale_tool'"
                    " (min_width/min_height/aspect_min/aspect_max) -> the"
                    f" Upscale panel's own min_side={migrated['min_side']}"
                    " + 1 filter condition (one-time; the old key stays"
                    " on disk unread from now on)"
                )
                panel_stored = dict(panel_stored)
                panel_stored.setdefault(
                    "up_minside", str(migrated["min_side"])
                )
                panel_stored.setdefault("conditions", migrated["conditions"])
        return panel_stored

    def _migrate_aspect_panel_settings(
        self, panel_stored: dict, stored: dict
    ) -> dict:
        """One-time migration (GUI rework Phase 14) of the retired
        standalone Aspect dialog's remembered ratio/filter —
        settings.json's old top-level ``aspect_ratio`` ([w, h]) and
        ``aspect_filter_conditions`` (or the even older scalar
        ``aspect_filter``, GUI rework Phase 4's own migration source)
        keys — into ``AspectSettingsPanel``'s OWN settings shape
        (``ratio``/``conditions``). A no-op once the panel has saved
        itself at least once under the NEW ``tool_panels`` key (same
        contract as ``_migrate_upscale_panel_settings`` above)."""
        if "ratio" in panel_stored:
            return panel_stored
        panel_stored = dict(panel_stored)
        saved_ratio = stored.get("aspect_ratio")
        if isinstance(saved_ratio, (list, tuple)) and len(saved_ratio) == 2:
            panel_stored["ratio"] = [str(saved_ratio[0]), str(saved_ratio[1])]
            self._log(
                "MIGRATION: standalone Aspect tool's remembered ratio"
                " (top-level 'aspect_ratio') -> the Aspect panel's own"
                " settings (one-time; the old key stays on disk unread"
                " from now on)"
            )

        if "conditions" not in panel_stored:
            saved_conditions = stored.get("aspect_filter_conditions")
            if isinstance(saved_conditions, list):
                panel_stored["conditions"] = saved_conditions
                self._log(
                    "MIGRATION: standalone Aspect tool's remembered"
                    " filter (top-level 'aspect_filter_conditions') ->"
                    " the Aspect panel's own settings (one-time; the old"
                    " key stays on disk unread from now on)"
                )
            else:
                legacy = stored.get("aspect_filter")
                if isinstance(legacy, dict):
                    try:
                        migrated = _migrate_legacy_aspect_filter(legacy)
                    except (TypeError, ValueError) as exc:
                        self._log(
                            f"MIGRATION: legacy aspect_filter {legacy!r} is"
                            f" unreadable ({exc}) — the Aspect panel"
                            " starts with no filter"
                        )
                    else:
                        self._log(
                            "MIGRATION: legacy 'aspect_filter' setting"
                            f" {legacy!r} -> {len(migrated)} condition(s)"
                            " on the Aspect panel (one-time; the old key"
                            " stays on disk unread from now on)"
                        )
                        panel_stored["conditions"] = migrated
        return panel_stored

    def _apply_settings(self, stored: dict) -> None:
        """Missing keys keep the current defaults. The queue is
        intentionally NOT restored — the app starts with an empty
        collection list every launch (owner 2026-07-18); only the
        output folder, per-agent settings, theme, geometry, zoom and
        the collapsed state persist (a stale ``sash`` key from an older
        settings.json is simply ignored)."""
        self._gemini_key = str(stored.get(GEMINI_KEY_SETTING, "") or "")
        # F2 (owner 2026-07-29): restore the persisted per-site quota
        # cooldowns (expired ones dropped), start the 30 s info-label
        # ticker, and WARN once at startup when any are still active —
        # information only, Start is never gated
        now = time.time()
        self._cooldowns = {
            key: float(until)
            for key, until in dict(
                stored.get("site_cooldowns", {})
            ).items()
            if key in self.agents and float(until) > now
        }
        self.root.after(1000, self._refresh_cooldown_labels)
        # F4e: restore the dashboard display mode (grid is the default)
        saved_mode = stored.get("dash_mode")
        if saved_mode in config.DASH_MODES:
            self._dashgrid.set_mode(saved_mode)
            self._render_dash_mode_btn()
        if self._cooldowns:
            lines = []
            for key, until in sorted(self._cooldowns.items()):
                left = int(until - now)
                lines.append(
                    f"{SITES[key].name}: limit resets in"
                    f" {left // 3600}:{left % 3600 // 60:02d}"
                )
                self._log(f"[{key}] COOLDOWN active — {lines[-1]}")
            self.root.after(
                800,
                lambda: messagebox.showwarning(
                    "Quota cooldown active",
                    "A previous run hit an image quota:\n\n"
                    + "\n".join(lines)
                    + "\n\nYou CAN still start — this is only a"
                    " reminder of what the site said.",
                    parent=self.root,
                ),
            )
        # PROMPT + IMAGE mode (faza 2, owner 2026-08-03): restore the
        # toggle + Reference folder; the visible reconcile
        # (_apply_prompt_image_state) runs once from __init__'s tail
        self._pi_section.apply_settings(
            dict(stored.get("prompt_image", {}))
        )
        saved_out = stored.get("output")
        if saved_out and Path(saved_out).is_dir():
            self.out_var.set(saved_out)
        elif saved_out:
            # never leave the field on a folder that does not exist:
            # done-detection reads <output>/_state and would otherwise
            # find nothing, offering every already-finished image again
            self._log(
                "saved output folder is gone — falling back to the"
                f" default: {DEFAULT_OUT_DIR}"
            )
        for key, panel in self.agents.items():
            agent_stored = dict(stored.get("agents", {}).get(key, {}))
            # per-agent upscale gate (GUI rework Phase 6): the NEW
            # 'up_minside' key wins when present; otherwise a ONE-TIME
            # LOUD migration reads the OLD four scalar fields
            # (up_minw/up_minh/up_aspmin/up_aspmax) exactly once — never
            # written back (up_minh is DROPPED: the two axes collapse
            # into one min-side spinner, and up_minw is used for it —
            # every shipped default and every real settings.json seen so
            # far already had up_minw == up_minh, so nothing observable
            # is lost in practice).
            if "up_minside" not in agent_stored and (
                "up_minw" in agent_stored or "up_minh" in agent_stored
                or "up_aspmin" in agent_stored or "up_aspmax" in agent_stored
            ):
                try:
                    migrated = _migrate_legacy_upscale_gate(
                        agent_stored.get("up_minw", UPSCALE_MIN_SIDE_DEFAULT),
                        agent_stored.get("up_aspmin", UPSCALE_ASPECT_MIN),
                        agent_stored.get("up_aspmax", UPSCALE_ASPECT_MAX),
                    )
                except (TypeError, ValueError) as exc:
                    self._log(
                        f"MIGRATION: {SITES[key].name} legacy upscale gate"
                        f" is unreadable ({exc}) — using the shipped"
                        " default upscale gate"
                    )
                else:
                    self._log(
                        f"MIGRATION: {SITES[key].name} legacy upscale gate"
                        " (up_minw/up_minh/up_aspmin/up_aspmax) ->"
                        f" up_minside={migrated['min_side']} + 1 filter"
                        " condition, now under 'up_minside'/"
                        "'up_filter_conditions' (one-time; the old keys"
                        " stay on disk unread from now on)"
                    )
                    agent_stored["up_minside"] = str(migrated["min_side"])
                    agent_stored["up_filter_conditions"] = migrated[
                        "conditions"
                    ]

            upscale_conditions = None
            saved_up_conditions = agent_stored.get("up_filter_conditions")
            if isinstance(saved_up_conditions, list):
                upscale_conditions = _parse_condition_dicts(
                    saved_up_conditions, self._log
                )
            panel.apply_settings(
                agent_stored, upscale_conditions=upscale_conditions
            )

        # GUI rework Phase 13/14: each standalone tool's PERSISTENT
        # settings panel (all four now) — same "missing key = keep
        # default" contract as every other field, mirroring the
        # "agents" loop above. upscale/aspect additionally get a
        # ONE-TIME LOUD migration from the retired standalone dialogs'
        # OLD top-level keys (_migrate_upscale_panel_settings/
        # _migrate_aspect_panel_settings) — a no-op once each panel has
        # saved itself at least once under this NEW "tool_panels" key.
        for slot, panel in self._tool_panels.items():
            panel_stored = dict(stored.get("tool_panels", {}).get(slot, {}))
            if slot == "upscale":
                panel_stored = self._migrate_upscale_panel_settings(
                    panel_stored, stored
                )
            elif slot == "aspect":
                panel_stored = self._migrate_aspect_panel_settings(
                    panel_stored, stored
                )
            conditions = None
            raw_conditions = panel_stored.get("conditions")
            if isinstance(raw_conditions, list):
                conditions = _parse_condition_dicts(raw_conditions, self._log)
            panel.apply_settings(panel_stored, conditions=conditions)

        saved_presets = stored.get(FILTER_PRESETS_SETTING)
        if isinstance(saved_presets, dict):
            self._filter_presets = {
                str(name): list(rows) for name, rows in saved_presets.items()
                if isinstance(rows, list)
            }

        if stored.get("geometry"):
            self.root.geometry(self._clamp_geometry(stored["geometry"]))

        # restore the collapsed/expanded Controls view LAST — geometry is
        # already sane, so the swap fits into a correctly-sized window (each
        # agent's fine-tune collapse was already applied in apply_settings)
        self._set_collapsed(bool(stored.get("controls_collapsed", False)))

    def _wire_persistence(self) -> None:
        """Meaningful changes debounce into a save; the queue buttons,
        zoom and the theme flip hook in at their own sites."""
        self.out_var.trace_add("write", lambda *_: self._schedule_save())
        for panel in self.agents.values():
            for var in panel.persist_vars():
                var.trace_add(
                    "write", lambda *_: self._schedule_save()
                )

    def _schedule_save(self) -> None:
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(1500, self._save_now)

    def _save_now(self) -> None:
        self._save_job = None
        self._settings = self._collect_settings()
        try:
            save_settings(self._settings)
        except OSError as exc:
            self._log(f"SETTINGS SAVE FAILED: {exc}")

    def _on_close(self) -> None:
        self._save_now()
        # drop every live job's backups (tools AND, since GUI rework
        # Phase 8, the two gen sites' own per-step pipeline backups),
        # then sweep the whole temp root (belt-and-braces for any orphan)
        for temp in list(self._job_temps.values()):
            temp.clear()
        self._job_temps.clear()
        jobtemp.clear_all()
        self.root.destroy()
