# Change Aspect Ratio — Flow

**About:** [description](../__about/aspect.md)

## Algorithm

```mermaid
flowchart TB
    A([change_aspect: path, ratio_w, ratio_h]) --> B{ratio_w/h > 0?}
    B -- no --> E1[["raise AspectError — bad target ratio"]]
    B -- yes --> C[open image; target = ratio_w/ratio_h; cur = W/H]
    C --> D{filter_mode set?}
    D -- IF, cur not in range --> R1[["return 'nothing' (filtered out)"]]
    D -- "IF NOT, cur in range" --> R1
    D -- passes / off --> F{"abs(cur - target) <= tol?"}
    F -- yes --> R2[["return 'nothing' (already at ratio)"]]
    F -- no --> G{cur < target?}
    G -- yes --> H["grow WIDTH: new_w = round(h * X/Y), new_h = h"]
    G -- no --> I["grow HEIGHT: new_h = round(w * Y/X), new_w = w"]
    H --> J[LANCZOS resize, mode preserved]
    I --> J
    J --> K[save as PNG]
    K --> R3[["return 'done'"]]
```

Pseudocode (language-neutral):

    FUNCTION change_aspect(path, ratio_w, ratio_h, tol, filter):
        IF ratio_w <= 0 OR ratio_h <= 0:
            RAISE AspectError("target ratio must be positive")

        image = open(path)
        target = ratio_w / ratio_h
        cur    = image.width / image.height

        IF filter.mode == "IF" AND cur NOT IN [filter.from, filter.to]:
            RETURN "nothing"
        IF filter.mode == "IF NOT" AND cur IN [filter.from, filter.to]:
            RETURN "nothing"

        IF |cur - target| <= tol:
            RETURN "nothing"          # already at ratio, byte-unchanged

        IF cur < target:
            # too tall/narrow for the target — grow the WIDTH
            new_w, new_h = round(height * ratio_w / ratio_h), height
        ELSE:
            # too wide for the target — grow the HEIGHT
            new_w, new_h = width, round(width * ratio_h / ratio_w)

        resized = LANCZOS_resize(image, new_w, new_h)   # mode/alpha kept
        save(resized, path, format="PNG")
        RETURN "done"
