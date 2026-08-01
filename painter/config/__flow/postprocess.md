# Postprocess Config — Flow

**About:** [description](../__about/postprocess.md)

## Structure

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A[postprocess.py] --> B[CROP THRESHOLDS]
    B --> B1[CROP_MARGIN_PX]
    B --> B2[CROP_INK_ALPHA, CROP_MIN_INK_PX]
    A --> C[EDGE-HALO CLEANUP]
    C --> C1[CLEAN_EDGE_ALPHA, CLEAN_EDGE_ENABLE]
    A --> D[BLACK-VOID REMOVAL + SAFETY GUARD]
    D --> D1[BLACK_VOID_MAX]
    D --> D2[SAFETY_MAX_REMOVE_FRAC / _WHITE]
    A --> E[BACKGROUND MODE]
    E --> E1[BG_MODE_AUTO / BLACK / WHITE / COLOR]
    E --> E2[BG_MODE_DEFAULT, BG_MODE_LABEL]
    A --> F[REACH]
    F --> F1[BG_REACH_EDGE / ALL]
    F --> F2[BG_REACH_DEFAULT, BG_REACH_LABEL]
    A --> G[CUSTOM COLOR + AUTO-DETECTION]
    G --> G1[BG_COLOR_DEFAULT, BG_COLOR_TOLERANCE_PCT]
    G --> G2[AUTO_CORNER_PX, AUTO_CORNER_AGREE_MAX]
    G --> G3[SAFETY_MAX_REMOVE_FRAC_COLOR]
```

## The three mechanisms are ONE (root Rule #19)

`bg_remove.remove_color_background` keys on per-channel distance from
a target colour; black (`#000000`) and white (`#FFFFFF`) are just two
targets sharing the same engine as a custom colour — the rule is
defined once (BG_MODE block), never enumerated per colour.
