# Driver Values

**Script:** [Driver Values (script)](../values.py) ·
**Folder:** [driver/](../___driver.md)

## Purpose
The driver's PURE, page-free vocabulary — value types and helpers that
touch no Playwright object at all. Nothing here needs a `Page`, which is
exactly why it lives apart from the five mixins: it is importable, and
testable, without a browser.

## Connections

### Uses
`dataclasses` only.

### Used by
[protocol](protocol.md), [wait](wait.md), [recovery](recovery.md) (the
`Baseline` reset on a new chat) and [Run Loop](../../__about/runner.md)
(`sniff_format`, through the package's public surface).

## Classes

### Baseline
The page-state snapshot taken BEFORE a submit (F1 protocol, owner
2026-07-29): assistant-turn count, last generated image src, user-turn
count and error-turn count. Everything after the send is judged RELATIVE
to it, which makes "grab the last visible image" — the duplicate-save
root cause — impossible. Frozen.

## Functions

- `sniff_format(data) -> str | None` — image format from magic
  bytes, so the runner can warn when saved bytes are not PNG.
- `normalize_text(text) -> str` — whitespace-collapsed, lowercased
  text for the composer/user-turn DOM comparisons (ProseMirror/Quill
  editors reflow whitespace and newlines).
