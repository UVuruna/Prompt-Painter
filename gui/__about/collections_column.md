# Collections Column

**Script:** [Collections Column (script)](../collections_column.py)

## Purpose
`CollectionsColumn` — the setup screens' shared RIGHT column (faza 3,
owner 2026-08-03, UV tačka 5: "raspored elemenata na levi i desni
panel isti kao Website Image GEN"). ONE component, two hosts (root
Rule C): the Website Image GEN setup screen and the API Image GEN
panel each render an instance — the Collections queue view
(Add/Remove/Clear/Add folder), the shared Output folder, the
Select-images door, the Prompt + Image toggle, the `Check` button
(moved out of the top strip, owner 2026-08-03 — it validates the
queue this column shows, so it lives beside it), and a
`PromptImageSection` in the column's lower half.

**The 50-50 height split is CONDITIONAL** (owner 2026-08-03: "ne može
da ostane prazan PROSTOR u DESNOM panelu"). `set_section_visible` is
the ONE door: with the mode ON both rows carry weight 1 in the
`colrow` uniform group (the tačka 3 rule); with it OFF the section is
`grid_remove`d, row 1 drops to weight 0 AND leaves the uniform group
— a uniform group still reserves a 0-weight row's slice, which was
exactly the dead gap under "Select images…" that also made the right
column outgrow the left settings panel.

STATE IS SHARED, WIDGETS ARE NOT: every column renders the same
`PainterGui._sheets` queue (mutations call each column's
`repaint_queue` — see [Settings Mixin](app_settings.md)'s
`_repaint_sheet_lists`), the same `out_var` StringVar (two entries,
one variable — Tk lockstep for free), and the same Prompt+Image
mode/folder vars (`_pi_enabled_var`/`_pi_ref_dir_var` — each column's
own `PromptImageSection` instance renders over them, so the mode
flips everywhere at once via `_apply_prompt_image_state`). Remove
uses THIS column's own listbox selection
(`gui._remove_sheet(listbox=…)`).

## Connections

### Uses
- [Prompt + Image Section](prompt_image.md) — one instance per
  column, over the shared mode vars
- [The Theme Engine](theme.md) — `skin_listbox`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/
  `rounded_entry`/`tk_font`
- `PainterGui` (duck-typed host) — the shared vars + the command
  methods every button calls (`_add_sheets`/`_add_sheets_folder`/
  `_remove_sheet`/`_clear_sheets`/`_pick_out`/`_select_images`/
  `_toggle_prompt_image`/`_schedule_save`)

### Used by
- [Build Mixin](app_build.md) — builds the website setup's primary
  column (its `sheet_list`/`btn_select`/`pi_section` become the
  canonical `PainterGui` aliases) and hands the API panel a
  `build_collections` factory for its own instance; every instance
  self-registers into `gui._collections_columns`
- [API Image GEN Panel](api_panel.md) — hosts the second instance as
  its right half
- [Settings Mixin](app_settings.md) — `_repaint_sheet_lists`/
  `_refresh_prompt_image` iterate the registered columns

## Classes

### CollectionsColumn
See Purpose above. `repaint_queue(paths)` refills this column's
listbox from the one shared queue truth.

## Design Decisions
- **Mirrored widgets over one state, never a reparenting trick.** Tk
  cannot show one widget in two places; syncing every view from the
  single `_sheets`/`out_var`/PI-vars truth keeps both hosts honest
  with ~30 lines of repaint glue instead of `in_=` geometry games.
