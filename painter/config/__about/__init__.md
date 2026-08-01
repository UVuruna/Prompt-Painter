# Config Package Index

**Script:** [Config Package Index (script)](../__init__.py)

## Purpose

The package's public interface. `painter/config/` was split by domain
into eleven submodules (root Rule #20 god-file split of the former
1,419-line `config.py`); this file re-exports the FULL public API of
every one of them — one explicit `from .X import (...)` block per
submodule, plus a matching `__all__` — so every existing
`config.X` / `from painter.config import X` call site anywhere in the
codebase kept working UNCHANGED across the split.

This is **not** a backward-compatibility shim (root Rule #6 does not
apply here): it IS the package's real interface, not a bridge to a
deleted old API. Verified at split time: a name-diff between the old
`config.py`'s module-level definitions and the new package's `dir()`
showed zero missing and zero extra names.

## Connections

### Uses
All eleven submodules, each imported explicitly by name (no
`import *`):
- [Paths](paths.md), [Formatters](formatters.md), [Sheet](sheet.md),
  [Postprocess](postprocess.md), [Upscale](upscale.md),
  [Aspect](aspect.md), [Theme](theme.md), [Jobs](jobs.md),
  [Job Temp Config](jobtemp.md), [AI](ai.md), [Sites](sites.md)

### Used by
- Every module in the project that does `from painter.config import X`
  or `painter.config.X` — [Main (Entry Point)](../../../__about/main.md),
  [GUI (folder)](../../../gui/___gui.md), and every `painter/*.py`
  engine module. See [Config (folder)](../___config.md)'s Connections
  section for the full external consumer registry (which submodule's
  constants which module reads).

## Public Names

Re-exports 196 names total, grouped by submodule of origin (`__all__`
mirrors this same grouping) — see each submodule's own `__about/` page
(linked above) for what each name is. No new class/function is
defined here; this file only imports and re-lists.
