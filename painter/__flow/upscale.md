# Upscale (Real-ESRGAN) — Flow

**About:** [description](../__about/upscale.md)

## Algorithm

```mermaid
flowchart TB
    A([upscale_if_small: path, min_w, min_h, aspect_min, aspect_max]) --> B[open image, ratio = W/H]
    B --> C{aspect_min <= ratio <= aspect_max?}
    C -- no --> R1[["return 'nothing' — not badge-shaped"]]
    C -- yes --> D{W >= min_w AND H >= min_h?}
    D -- yes --> R2[["return 'nothing' — already big enough"]]
    D -- no --> E[ensure_binary: download/verify Real-ESRGAN exe once]
    E --> F[run binary at NATIVE 4x with the configured model]
    F --> G[factor = min(1.0, max(min_w/out_w, min_h/out_h))]
    G --> H{factor < 1.0?}
    H -- yes --> I[LANCZOS downscale by factor]
    H -- no --> J[keep full 4x result]
    I --> K[save PNG]
    J --> K
    K --> R3[["return 'done'"]]
```

Pseudocode (language-neutral):

    FUNCTION upscale_if_small(path, min_width, min_height, aspect_min, aspect_max):
        (width, height) = size_of(path)
        ratio = width / height
        IF NOT (aspect_min <= ratio <= aspect_max):
            RETURN "nothing"                      # not the circular/badge class
        IF width >= min_width AND height >= min_height:
            RETURN "nothing"                      # already big enough

        exe = ensure_binary()                     # download+verify once per process
        upscaled = RUN exe AT NATIVE 4x (never 2x/3x — corrupts output)

        # scale the 4x result down by the SMALLEST factor that still
        # keeps BOTH minimums — the binding axis lands exactly on target
        factor = MIN(1.0, MAX(min_width / upscaled.width,
                               min_height / upscaled.height))
        IF factor < 1.0:
            upscaled = LANCZOS_resize(upscaled, factor)
        SAVE upscaled AS PNG over path
        RETURN "done"
