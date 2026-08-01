# DayNightSwitch — Flow

**About:** [description](../__about/switch.md)

## Click -> flip -> slide

```mermaid
flowchart TB
    A([user clicks the switch]) --> B[flip self._on; pick theme name day/night]
    B --> C["apply_theme(name, animate=True)\n— snapshot-cover cross-fade hides the app's repaint"]
    C --> D[schedule a settings save]
    D --> E["_animate() — starts the knob slide\n(runs CONCURRENTLY under the fade cover)"]
    E --> F[cover fades out over its own duration]
    F --> G[by the time the cover is gone, the knob has\nalready slid to (or near) its target x]
```

The theme flip and the knob slide are two INDEPENDENT animations that
happen to start together — the cover fade owns visual coherence
(nothing looks half-repainted), the knob slide is pure flourish that
the owner sees revealed as the cover clears.

## Knob slide (`_animate`)

```mermaid
flowchart TB
    A([_animate]) --> B[cancel any in-flight slide job]
    B --> C[target = x_on if on else x_off; start = current knob x]
    C --> D[frames = round SWITCH_ANIM_MS / SWITCH_FRAME_MS]
    D --> E[i = 0]
    E --> F[step]
    F --> G[i += 1; t = i / frames]
    G --> H["ease = smoothstep(t) = t*t*(3 - 2*t)"]
    H --> I[knob_x = start + (target - start) * ease]
    I --> J[_redraw]
    J --> K{i < frames?}
    K -- yes --> L["schedule step again after SWITCH_FRAME_MS"]
    L --> F
    K -- no --> M[knob_x = target exactly — no float drift]
```

A re-click mid-slide cancels the running `after()` chain and starts a
fresh one from the CURRENT (possibly mid-flight) `knob_x` — the slide
never jumps or restarts from the old rest position.

## Redraw — which image, which track

Each `_redraw` is a plain lookup, no computation beyond one
comparison:

    FUNCTION redraw():
        midpoint = (x_off + x_on) / 2
        day = knob_x > midpoint          # which SIDE the knob currently reads as
        draw track_day if day else track_night, centred in the canvas
        base = "sun" if day else "moon"
        key = base + "_hover" if hovering else base
        draw imgs[key], centred at (knob_x + knob_diameter/2, canvas mid-y)

The track hard-swaps at the knob's midpoint rather than cross-fading —
the slide itself is the transition the eye tracks; a simultaneous
track cross-fade would be motion the owner never asked for.
