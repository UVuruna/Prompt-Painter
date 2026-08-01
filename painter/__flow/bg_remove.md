# Background Remover — Flow

**About:** [description](../__about/bg_remove.md)

## Algorithm

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph PLAN["plan(img, mode) — pick the recipe"]
        direction TB
        P0[convert RGBA] --> P1{already transparent
        beyond TRANSPARENT_FRAC?}
        P1 -- yes --> P2[["'skip-transparent'"]]
        P1 -- no --> P3{mode == COLOR?}
        P3 -- yes --> P4[["'color': target=color, dist=tolerance"]]
        P3 -- no --> P5{mode == BLACK?}
        P5 -- yes --> P6[["'black': target=#000, void ceiling + feather"]]
        P5 -- no --> P7{mode == WHITE?}
        P7 -- yes --> P8[["'white': target=#FFF, adaptive two-threshold ramp"]]
        P7 -- no --> P9{border sniff: white?}
        P9 -- yes --> P8
        P9 -- no --> P10{border sniff: black?}
        P10 -- yes --> P6
        P10 -- no --> P11{four corners agree?}
        P11 -- yes --> P12[["'color': target=agreed colour"]]
        P11 -- no --> P13[["'skip-ambiguous' (report border_hex)"]]
    end

    subgraph ENGINE["remove_color_background(img, target, dist_full, dist_edge, sigma, reach)"]
        direction TB
        E1[dist = Chebyshev distance to target, per pixel] --> E2[match = dist <= dist_edge]
        E2 --> E3{reach == ALL?}
        E3 -- yes --> E4[background = match]
        E3 -- no --> E5[background = match pixels reachable
        from the frame by flood fill]
        E4 --> E6{dist_edge > dist_full?}
        E5 --> E6
        E6 -- yes --> E7[soft ramp: alpha 0 at dist_full,
        255 at dist_edge]
        E6 -- no --> E8[hard cut at dist_edge,
        feathered by sigma]
        E7 --> E9[compose RGBA, removed_frac = mean(background)]
        E8 --> E9
    end

    PLAN --> ENGINE
    ENGINE --> G{removed_frac > SAFETY guard for this action?}
    G -- yes --> H[["abort — original untouched (caller reports)"]]
    G -- no --> I[["save cleared image"]]
```

Pseudocode (language-neutral):

    FUNCTION plan(image, mode, color, tolerance_pct):
        IF image mostly already transparent: RETURN "skip-transparent"
        border = sample the outer ~1% frame band
        IF mode == "color":  RETURN color_plan(color, tolerance_pct)
        IF mode == "black":  RETURN black_plan()
        IF mode == "white":  RETURN white_plan(border)          # adaptive
        # AUTO mode — sniff, then ask the corners
        IF border looks white:  RETURN white_plan(border)
        IF border looks black:  RETURN black_plan()
        agreed = corner_background_color(image)   # 4 corners, median each
        IF agreed is not None: RETURN color_plan(agreed, tolerance_pct)
        RETURN "skip-ambiguous"                     # report border colour seen

    FUNCTION remove_color_background(image, target, dist_full, dist_edge, sigma, reach):
        dist  = per_pixel MAX_CHANNEL(|pixel - target|)          # Chebyshev
        match = dist <= dist_edge
        IF reach == "all":
            background = match
        ELSE:  # "edge" (default)
            background = match pixels reachable from the image
                         border by walking only through other
                         matching pixels (flood fill inward)

        IF dist_edge > dist_full:
            alpha = ramp 0..255 between dist_full and dist_edge     # soft edge
        ELSE:
            alpha = 0 where background else 255                    # hard cut
            IF sigma > 0: alpha = gaussian_blur(alpha, sigma)       # ~1px feather

        removed_frac = mean(background)
        RETURN (compose(rgb, alpha), removed_frac)

    FUNCTION caller (process_file / postprocess.remove_background):
        removal = plan(...)
        IF removal.action starts with "skip": RETURN removal.action
        (out, removed) = remove_color_background(removal's params)
        IF removed > SAFETY_GUARD[removal.action]:
            RETURN "skip-risky" / "unclear"          # original untouched
        SAVE out
        RETURN removal.action
