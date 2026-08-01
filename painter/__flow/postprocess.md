# Postprocess (Background Removal + Crop) — Flow

**About:** [description](../__about/postprocess.md)

## Algorithm

```mermaid
flowchart TB
    subgraph BG["remove_background(path, mode, color, tolerance, reach)"]
        direction TB
        A1[plan(image, mode) — decide the recipe] --> A2{action?}
        A2 -- skip-transparent --> A3[["return 'nothing'"]]
        A2 -- skip-ambiguous --> A4[log the sniffed border colour] --> A5[["return 'unclear'"]]
        A2 -- white/black/color --> A6[apply_plan: clear region, get removed_frac]
        A6 --> A7{removed_frac > guard for this action?}
        A7 -- yes --> A8[log which guard fired] --> A5
        A7 -- no --> A9[save PNG] --> A10[["return 'done'"]]
    end

    subgraph CROP["crop_transparent(path, ...)"]
        direction TB
        B1{clean_edge_enable?}
        B1 -- yes --> B2[clean_edge_halo: zero faint border-connected pixels]
        B1 -- no --> B3
        B2 --> B3[content_bbox: ink-based box + margin]
        B3 --> B4{box is None?}
        B4 -- yes --> B5[["return 'nothing' — no content to crop to"]]
        B4 -- no --> B6{box+margin == full frame?}
        B6 -- yes --> B7[["return 'nothing' — 0px change, halo cleanup discarded"]]
        B6 -- no --> B8[crop + save PNG] --> B9[["return 'done'"]]
    end
```

Pseudocode (language-neutral):

    FUNCTION remove_background(path, mode, color, tolerance_pct, reach):
        removal = plan(image, mode, color, tolerance_pct)   # bg_remove.plan
        IF removal.action == "skip-transparent": RETURN "nothing"
        IF removal.action == "skip-ambiguous":
            LOG("background unclear — border looked like", removal.border_hex)
            RETURN "unclear"

        (cleared_image, removed_frac) = apply_plan(image, removal, reach)
        guard = SAFETY_GUARD[removal.action]      # black tight, white/color loose
        IF removed_frac > guard:
            LOG("removal would clear", removed_frac, "over guard", guard)
            RETURN "unclear"                       # ORIGINAL left untouched

        SAVE cleared_image AS PNG over path
        RETURN "done"

    FUNCTION crop_transparent(path, clean_edge_enable, margin, ink_alpha, min_ink_px):
        rgba = open(path) as RGBA
        IF clean_edge_enable:
            rgba = clean_edge_halo(rgba)           # zero faint border-connected pixels

        box = content_bbox(rgba, ink_alpha, min_ink_px)   # ink-based content box
        IF box IS None:
            RETURN "nothing"                        # nothing solid to crop to

        (left, top, right, bottom) = box expanded by margin, clamped to image size
        IF (right - left, bottom - top) == (width, height):
            RETURN "nothing"                         # 0px change — halo cleanup discarded
        SAVE rgba.crop(left, top, right, bottom) AS PNG over path
        RETURN "done"
