# Doc Window — Flow

**About:** [description](../__about/doc_window.md)

## Layout

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph WIN["DocWindow"]
        BAR["Top bar: hint (left)  ·  Copy (for AI) / Close (right)"]
        FIXBAR["OPTIONAL fix bar: status label (left)  ·  IMAGE FIX / WEBSITE FIX (right) — built only when a fix callback was passed"]
        TXT["Scrollable Text: rendered Markdown  +  optional appended image"]
    end
    BAR --> FIXBAR --> TXT
```

## Algorithm — two-phase sizing (width first, then content-fit height)

```
_apply_width():                      # runs in __init__, BEFORE render
    if image_path given:
        width = image.native_width + DOC_IMG_PAD_PX      # IMAGE mode
    else:
        width = screen_height * DOC_HEIGHT_FRAC * DOC_A4_RATIO   # TEXT mode
    width = clamp(width, DOC_MIN_W, screen_width * DOC_MAX_FRAC)
    set geometry(width x a tall PROVISIONAL height)       # real height unknown yet

_render(markdown) + _append_image()  # fills the Text at the now-fixed width

on first <Map> event (window is actually laid out on screen):
    _fit_height():
        content_h = Text.count("1.0", "end", "ypixels")   # the REAL wrapped height
        needed = content_h + chrome_height(bars + padding)
        height = clamp(needed, DOC_MIN_H, screen_height * DOC_MAX_FRAC)
        set geometry(target_width x height)                # snaps to real content
```

Measuring in `__init__` would read a zero-height Text (nothing is
laid out until the window is mapped) — that is why the fit happens on
`<Map>`, one-shot, rather than at construction time.

## Algorithm — Fixer-AI manual buttons (worker-thread + poll loop)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TD
    A["IMAGE FIX / WEBSITE FIX clicked"] --> B["disable BOTH buttons · status = 'Fixing…'"]
    B --> C["spawn background thread: result = worker()"]
    C --> D["thread puts (which, result) on the private queue"]
    B --> E["arm_fix_poll(): after(AI_POLL_MS, poll_fix)"]
    E --> F{"window still exists?"}
    F -->|no| G["stop — the result is moot"]
    F -->|yes| H{"message on queue?"}
    H -->|no| E
    H -->|yes| I["_fix_result_ui(which, result) -> (status, enable_image?, enable_website?)"]
    I --> J["update status label + re-enable the button(s) the pure mapping says to"]
```

Both buttons disable together while one fix is in flight — a second
fix started before the first lands would race the same file. The pure
decision (`_fix_result_ui`, in `gui/logic.py`) is Tk-free and unit
tested on its own; this window only applies its 3-tuple to real
widgets.
