# Shared Filter Framework — Flow

**About:** [description](../__about/filters.md)

## Algorithm

```mermaid
flowchart TB
    A([matches: width, height, conditions]) --> B{any conditions left?}
    B -- no --> R1[["return True — nothing left to fail"]]
    B -- yes --> C[take next condition]
    C --> D{kind?}
    D -- ASPECT_EXACT / ASPECT_RANGE --> E1["in_range = lo <= w/h <= hi"]
    D -- ANY_SIDE --> E2["in_range = lo <= min(w,h) AND max(w,h) <= hi"]
    D -- WIDTH --> E3["in_range = lo <= w <= hi"]
    D -- HEIGHT --> E4["in_range = lo <= h <= hi"]
    D -- unknown --> X1[["raise ValueError — bad kind"]]
    E1 --> F
    E2 --> F
    E3 --> F
    E4 --> F
    F{polarity?}
    F -- IF --> G1[passed = in_range]
    F -- IF NOT --> G2[passed = NOT in_range]
    F -- unknown --> X2[["raise ValueError — bad polarity"]]
    G1 --> H{passed?}
    G2 --> H
    H -- no --> R2[["return False — one condition vetoed the image"]]
    H -- yes --> B
```

Pseudocode (language-neutral):

    FUNCTION matches(width, height, conditions) -> bool:
        FOR EACH condition IN conditions:
            in_range = MEASURE(condition.kind, width, height)
                          IN [condition.lo, condition.hi]
            IF condition.polarity == "IF":
                passed = in_range
            ELSE IF condition.polarity == "IF NOT":
                passed = NOT in_range
            ELSE:
                RAISE ValueError("unknown polarity")
            IF NOT passed:
                RETURN False        # AND stacking — one failure vetoes all
        RETURN True                 # every condition passed (or none exist)

    FUNCTION MEASURE(kind, width, height):
        IF kind IN (ASPECT_EXACT, ASPECT_RANGE): RETURN width / height
        IF kind == ANY_SIDE:  RETURN (min(width, height), max(width, height))
                               # tested as lo <= min AND max <= hi
        IF kind == WIDTH:     RETURN width
        IF kind == HEIGHT:    RETURN height
        RAISE ValueError("unknown filter kind")
