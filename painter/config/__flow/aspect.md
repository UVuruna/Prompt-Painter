# Aspect Config — Flow

**About:** [description](../__about/aspect.md)

## Structure

```mermaid
flowchart TB
    A[aspect.py] --> B[ASPECT TOOL — CORE + LEGACY FILTER]
    B --> B1[ASPECT_TOL, ASPECT_DEFAULT_W/H]
    B --> B2[ASPECT_FILTER_OFF/IF/IF_NOT, ASPECT_FILTER_MODES]
    B --> B3[ASPECT_FILTER_DEFAULT_FROM/TO]
    B --> B4[ASPECT_LABEL_DECIMALS]
    A --> C[SHARED FILTER FRAMEWORK]
    C --> C1[FILTER_KIND_* + FILTER_KINDS]
    C --> C2[FILTER_POLARITY_IF / IF_NOT]
    C --> C3[FILTER_PRESETS_SETTING]
    C --> C4[FILTER_ASPECT_EXACT_TOL]
```

The shared filter framework (C) is a LATER phase meant to eventually
replace the legacy scalar filter (B2/B3) — nothing here is wired into
a tool yet beyond the engine constants; migrating existing tools onto
it is tracked separately (see [Config (folder)](../___config.md)'s
Design Decisions).
