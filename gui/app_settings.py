"""SettingsMixin — the queue/sheet helpers, prerequisite handlers, AI
features gate, and settings persistence.

Godfile refactor step 7/8 (see gui/___gui.md): the fifth of PainterGui's
five mixins (see gui/app.py). Owns the Collections queue (Add…/Add
folder…/Remove/Clear — ``_queue_sheets``/``_add_sheets``/
``_add_sheets_folder``/``_remove_sheet``/``_clear_sheets``), the sheet
parsing/planning helpers shared by the site jobs (``_parse_all``/
``_out_base``/``_done_on_disk``/``_plan``), the dashboard row viewers
(``_show_node``/``_show_folder_excerpt``), the top-strip "prerequisite"
button handlers (``_open_chrome``/``_check_sheets``/``_select_images``/
``_open_instructions``/``_new_collection_ai``/``_open_key_wizard``), the
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
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from painter import config, jobtemp
from painter.config import (
    DEFAULT_OUT_DIR,
    FILTER_PRESETS_SETTING,
    GEMINI_KEY_SETTING,
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
from .dialogs import AiKeyWizard, AiSheetDialog
from .logic import (
    _migrate_legacy_aspect_filter,
    _migrate_legacy_upscale_gate,
    _parse_condition_dicts,
)
from .select_window import SelectWindow
from .widgets import folder_of


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
        image opens its own prompt PLUS the saved image below it (when
        the destination file already exists)."""
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
            item = next(
                (it for it in sheet.items if it.drop_path == info["drop"]),
                None,
            )
            if item is None:
                messagebox.showinfo(
                    "PromptPainter",
                    f"No prompt found for {info['drop']} in {source.name}.",
                )
                return
            md = (
                f"# {item.title}\n\n`{item.drop_path}`\n\n"
                f"```\n{item.prompt}\n```\n"
            )
            dest = self._out_base() / dest_for(item.drop_path, site_key)
            gui.DocWindow(
                self.root, item.drop_path, md, copy_text=item.prompt,
                hint="The prompt for this one image.",
                image_path=dest if dest.is_file() else None,
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
                self.sheet_list.insert("end", path.name)
        self._schedule_save()

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

    def _remove_sheet(self) -> None:
        for index in reversed(self.sheet_list.curselection()):
            self.sheet_list.delete(index)
            del self._sheets[index]
        self._schedule_save()

    def _clear_sheets(self) -> None:
        self.sheet_list.delete(0, "end")
        self._sheets.clear()
        self._schedule_save()

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

    def _open_chrome(self) -> None:
        # both sites' tabs — a site "participates" by being Started,
        # and a spare logged-in tab costs nothing
        urls = tuple(SITES[k].url for k in sorted(SITES))
        self.status_var.set("opening Chrome …")

        def work():
            from painter.chrome import ChromeError, ensure_chrome

            try:
                state = ensure_chrome(urls)
            except ChromeError as exc:
                self._q.put(f"CHROME ERROR: {exc}")
                self._q.put(("__status__", "idle"))
                return
            if state == "launched":
                self._q.put(
                    "Chrome opened with the PromptPainter profile — log in"
                    " on each site tab once, then press Start."
                )
            else:
                self._q.put("Chrome already running — ready.")
            self._q.put(("__status__", "idle"))

        threading.Thread(target=work, daemon=True).start()

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
        SelectWindow(self, sheets)

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
        """'New collection (AI)…' — the request -> questions -> sheet
        flow lives in its own dialog; only the key gate sits here."""
        if not self._ensure_ai_key():
            return
        AiSheetDialog(self.root, self)

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
            # the AI features' credential (owner 2026-07-20): held on
            # the GUI so the whole-dict save round-trips it; painter.ai
            # reads it back from settings.json per call
            GEMINI_KEY_SETTING: self._gemini_key,
            FILTER_PRESETS_SETTING: {
                name: list(rows) for name, rows in self._filter_presets.items()
            },
            "agents": {
                key: panel.get_settings()
                for key, panel in self.agents.items()
            },
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
