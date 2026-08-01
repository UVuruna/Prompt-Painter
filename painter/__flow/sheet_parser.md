# Sheet Parser — Flow

**About:** [description](../__about/sheet_parser.md)

## Algorithm

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A([parse_sheet: read lines]) --> B{next line?}
    B -- none left --> Z[flush any pending entry] --> ZZ{theme found?}
    ZZ -- no --> E1[["raise SheetError — no H1"]]
    ZZ -- yes --> R[["return Sheet(theme, items, skipped, problems)"]]

    B -- fence ``` --> F1[flush pending: heading interrupted]
    F1 --> F2[collect block lines until closing fence]
    F2 --> F3{pending entry waiting?}
    F3 -- yes --> F4[PromptItem = pending + this block] --> B
    F3 -- no --> B

    B -- heading # --> H1{first H1 and theme unset?}
    H1 -- yes --> H2[theme = heading text] --> B
    H1 -- no --> H3{legacy heading entry:
    one backticked image name?}
    H3 -- yes --> H4[register_entry legacy=True] --> B
    H3 -- no --> H5[section heading: set 'poison' advice
    if skip-marked; capture dir token
    for bare-bold entries below] --> B

    B -- blank line --> B
    B -- paragraph --> P1{starts with **bold**?}
    P1 -- no --> B
    P1 -- yes --> P2[extract bold spans, arrow target,
    skip-marker span, legacy shapes]
    P2 --> P3{drop path found
    (arrow / legacy bold-token / bare-bold-under-dir)?}
    P3 -- no --> P4{marker span present?}
    P4 -- yes, entry named --> P5[SkippedItem — no prompt to load] --> B
    P4 -- yes, standalone note --> P6[set 'poison' for the rest of section] --> B
    P4 -- no --> B
    P3 -- yes --> P7[flush previous pending entry]
    P7 --> P8[validate drop path: no escape,
    image extension, not duplicate]
    P8 -- invalid, non-legacy --> P9[Problem reported] --> B
    P8 -- valid --> P10[register as pending entry,
    advice = own marker or section poison,
    optional input_image from ← arrow] --> B
```

Pseudocode (language-neutral):

    FUNCTION parse_sheet(path):
        lines = read_file_lines(path)
        theme = None; items = []; skipped = []; problems = []
        pending = None            # entry awaiting its fenced prompt
        poison  = None            # active section-level advice
        section_dir = None        # legacy bare-bold drop directory

        FOR EACH line in lines:
            IF line is a fence start (```):
                flush_pending("a heading interrupts it")
                block = collect lines until closing fence
                IF pending is not None:
                    items.append(PromptItem(pending fields, prompt=block))
                    pending = None
                CONTINUE

            IF line is a heading (#...):
                flush_pending("a heading interrupts it")
                IF this is the FIRST "# " line AND theme is unset:
                    theme = heading text; CONTINUE
                IF heading carries exactly one backticked image name:
                    register_entry(title, image_name, legacy=True)
                ELSE:
                    poison = heading text IF it carries a skip marker ELSE None
                    section_dir = the one backticked "dir/" token, if any
                CONTINUE

            IF line is blank: CONTINUE

            # otherwise: a paragraph — collect consecutive non-blank lines
            paragraph = collect lines until blank/fence/heading
            IF NOT paragraph.startswith("**"): CONTINUE   # prose, not an entry

            title = first bold span, whitespace-normalized
            drop  = the "→ `path.png`" arrow target, OR a legacy shape
                    (whole-paragraph bold token, or bare bold under a
                    dir-carrying section) — whichever the paragraph matches
            marker = a skip-marker found inside a bold span, if any

            IF drop is None:
                IF marker names THIS entry: skipped.append(SkippedItem(...))
                ELSE IF marker is a standalone note: poison = marker
                CONTINUE                                   # prose bold, not an entry

            flush_pending("the next entry starts")
            VALIDATE drop (no path escape, image extension, not a duplicate)
                — invalid AND non-legacy -> problems.append(...); CONTINUE
            input_image = the "← `ref.ext`" arrow target, if present and valid
            pending = (title, drop, line_no, marker OR poison, input_image)

        flush_pending("the sheet ends")
        IF theme is None: RAISE SheetError("no H1 theme")
        IF items is empty AND skipped is empty:
            problems.append("sheet contains no image entries")
        RETURN Sheet(theme, items, skipped, problems)
