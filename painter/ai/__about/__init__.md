# AI Package Index

**Script:** [AI Package Index (script)](../__init__.py)

## Purpose

A PURE re-export shell (the same shape `painter/config` and `gui`
already use), so every existing `from painter import ai` /
`ai.generate_image(...)` call site and every
`monkeypatch.setattr(ai_module, "edit_image", fake)` in the suite
keeps working unchanged across the root Rule #20 package split
(2026-07-30, was one 1,198-line `ai.py`). Re-exports the FULL public
API of [Gemini REST Client](client.md), [Sheet-Generator
Flow](sheet_flow.md), [Flag Memory](flags.md) and [Image
Checker](checks.md) — one explicit `from .module import (...)` block
each.

The ONE thing that must name a submodule directly, never the
package: a patch of an INTERNAL, `painter.ai.client._urlopen` (the
HTTP layer), since `_send_request` reads it from its own module
globals.

## Connections

### Uses
- [Gemini REST Client](client.md), [Sheet-Generator
  Flow](sheet_flow.md), [Flag Memory](flags.md), [Image
  Checker](checks.md) — re-exports every public name from all four

### Used by
- [GUI (folder)](../../../gui/___gui.md) — every `ai.X` call site
- [Tests (folder)](../../../tests/___tests.md) — mocked-HTTP client
  tests, flow tests, flag round-trips
