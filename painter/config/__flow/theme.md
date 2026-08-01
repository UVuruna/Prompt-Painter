# Theme Config — Flow

**About:** [description](../__about/theme.md)

## Structure

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A[theme.py] --> B[PALETTES — THEMES + PAIR HELPERS]
    A --> C[SOLID BUTTON FILLS]
    A --> D[SWITCH — GEOMETRY + ANIMATION TIMING]
    A --> E[VISUAL MECHANICS — TRANSITION FADE + RESIZE DEBOUNCE]
    A --> F[SWITCH ART — TRACK SVGS + KNOB HIGHLIGHT]
    A --> G[SWITCH ART — MOON KNOB]
    A --> H[SWITCH ART — SUN KNOB]
```

Nested view of the two biggest sections:

- PALETTES
  - `THEMES["night"]` — darkly, verbatim
  - `THEMES["day"]` — `painter_day`, the custom light theme
  - `theme_pair` / `status_pair` — day/night lookup helpers
- SWITCH ART — MOON KNOB
  - radial gradient (center → edge)
  - 7 craters (diameter, x, y) with lit rims
  - terminator shading (light direction, dark floor, soft band)
  - deterministic surface noise (fixed seed)
- SWITCH ART — SUN KNOB
  - radial gradient (center → edge)
  - blurred glow disc behind the knob
