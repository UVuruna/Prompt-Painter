# Jobs Config — Flow

**About:** [description](../__about/jobs.md)

## Structure

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A[jobs.py] --> B[DASHBOARD PER-JOB PANELS]
    B --> B1[JOB_ORDER, JOB_TOOL_KINDS]
    B --> B2[JOB_LABEL, JOB_LOGO, JOB_COLORS, JOB_METRIC]
    A --> C[DASHBOARD GRID SIZING + DISPLAY MODES]
    C --> C1[DASH_CARD_MIN_W, DASH_GRID_MAX_COLS]
    C --> C2[DASH_MODE_GRID / SLIDER]
    A --> D[DASHBOARD STATUS BADGES]
    D --> D1[BADGES, BADGE_ACTION_STEPS]
    D --> D2[badge_keys_for]
    A --> E[MAIN MENU — GEOMETRY + MENU_TILES]
    E --> E1[MenuTile dataclass]
    E --> E2[MENU_TILES — 8 tiles]
    A --> F[MAIN MENU — TILE_JOB_KINDS MAPPING]
    F --> F1[TILE_JOB_KINDS]
    F --> F2[tile_for_kind]
```

## Algorithm — `badge_keys_for`

```mermaid
flowchart TB
    A["actions string, retried flag"] --> B[split actions on ',']
    B --> C[FOR EACH part: split 'STEP: status']
    C --> D{step in BADGE_ACTION_STEPS<br/>AND status == BADGE_DONE_STATUS?}
    D -- yes --> E[add badge key to earned set]
    D -- no --> F[ignore — unknown/failed segment]
    E --> G{retried?}
    F --> G
    G -- yes --> H[add 'retry' to earned]
    G -- no --> I[keep earned as-is]
    H --> J[return earned keys, in BADGES render order]
    I --> J
```

Pseudocode:

    FUNCTION badge_keys_for(actions, retried=False):
        earned = {}
        FOR EACH part IN actions.split(","):
            step, status = part.partition(":")
            key = BADGE_ACTION_STEPS.get(step.strip())
            IF key is not None AND status.strip() == BADGE_DONE_STATUS:
                earned.add(key)
        IF retried: earned.add("retry")
        RETURN tuple(key for key in BADGES if key in earned)  # render order
