# Formatters

**Script:** [Formatters (script)](../formatters.py)

## Purpose

Small human-readable formatters shared by the run-loop report and the
GUI dashboard: durations, file sizes, and tool-metric percentages,
each with a precision rule tuned so a small real value never rounds
away to a meaningless `'0'`.

## Connections

### Uses
Nothing — a leaf module (pure functions, no imports).

### Used by
- [Run Loop](../../__about/runner.md) — the per-sheet report text
- GUI dashboard (`gui/dash_panels.py`, `gui/dash_helpers.py`) — the
  live per-collection / per-run numbers
- Re-exported by [Config Package Index](__init__.md)

## Functions

### `fmt_duration(seconds) -> str`
A short whole-second human duration: `'3m 12s'`, `'48s'`.

### `fmt_op_duration(seconds) -> str`
Like `fmt_duration`, but with sub-second precision below 10s
(`'0.2s'`, `'3.4s'`) — the fast in-place tools (BG/Crop/Aspect) run in
fractions of a second, and whole-second `fmt_duration` would flatten
every one of them to `'0s'`. At 10s and up it matches
`fmt_duration`'s whole-second/minute form.

### `fmt_size(num_bytes) -> str`
A short human file size: `'1.4 MB'`, `'812 KB'`, `'70 B'`.

### `fmt_pct(value) -> str`
A tool metric percentage, magnitude-scaled precision (owner
2026-07-19): below 10 → 2 decimals (`'0.08'`, `'9.99'`), 10 and up →
1 decimal (`'10.0'`, `'300.0'`). Returns the NUMBER only — callers
append the `%`. So a 3px crop reads `'0.24'`, never a rounded-away
`'0'`.
