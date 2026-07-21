# App (composition)

**Script:** [App (script)](app.py)

## Purpose
`PainterGui` itself — composed from the five responsibility mixins
(root Rule #20 god-file refactor, step 7/8; see
[GUI (folder)](___gui.md)): [Build Mixin](app_build.md) (the
constructor + widget construction), [View Mixin](app_views.md) (the
Main Menu / running-view state machine), [Site Jobs Mixin](app_jobs.md)
(the site + API-image run loop, dashboard dispatch, Checker AI, Fixer
AI), [Tool Jobs Mixin](app_tools.md) (the four standalone tools + the
AI image checker) and [Settings Mixin](app_settings.md) (queue/sheet
management, prerequisite actions, settings persistence). `PainterGui`
contributes no method bodies of its own — every method it exposes is
defined on exactly one mixin; the class body here is just the MRO
glue. Also holds `main()` (the CLI-less entry point `main.py` calls
with no arguments) and the `if __name__ == "__main__":` guard, both
moved out of `gui/__init__.py` verbatim alongside the class.

## Classes

### PainterGui
`class PainterGui(BuildMixin, ViewMixin, SiteJobsMixin, ToolJobsMixin,
SettingsMixin):` — no body beyond a docstring. `BuildMixin` is first
in the MRO (and the only base with `__init__`), so
`PainterGui(root)` runs `BuildMixin.__init__` unchanged; every other
mixin's methods run on the same instance via `self.`.

## Connections

### Uses
- [Build Mixin](app_build.md), [View Mixin](app_views.md),
  [Site Jobs Mixin](app_jobs.md), [Tool Jobs Mixin](app_tools.md),
  [Settings Mixin](app_settings.md) — the five bases
- `ttkbootstrap` — `main()`'s `tb.Window(themename="darkly")`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py`'s `from .app import
  PainterGui, main` keeps `gui.PainterGui`/`from gui import
  PainterGui` (and `main`) working for every existing caller
- [Main (Entry Point)](../main.md) — `from gui import PainterGui`

## Design Decisions
- **Why a thin composition file instead of folding `PainterGui` into
  one of the mixins.** Any single mixin "owning" the class definition
  would misleadingly suggest that mixin is somehow more central than
  the other four; a standalone file whose only job is `class
  PainterGui(BuildMixin, ViewMixin, SiteJobsMixin, ToolJobsMixin,
  SettingsMixin): ...` makes the composition — and the MRO order,
  which matters only in that `BuildMixin` must run its `__init__`
  first — the explicit, complete story in one place.
- **`main()` followed the class here, not into `BuildMixin`.** It is
  the module-level entry point for the WHOLE composed class (`root =
  tb.Window(...); PainterGui(root); root.mainloop()`), not a
  `BuildMixin`-specific concern — grouping it with the class it
  constructs, in the same file, mirrors where it lived beside
  `class PainterGui:` before the split.
