# Image Checker — Flow

**About:** [description](../__about/checks.md)

## Algorithm

```mermaid
flowchart TB
    subgraph ONE["check_one_image(src, out_base, instructions)"]
        direction TB
        A1[model = model_for('vision') if not given] --> A2[key = flag_key(src, out_base)]
        A2 --> A3[call check(src, instructions, model)]
        A3 -- AiError --> A4[["return kind='error', raw=exc text"]]
        A3 -- raw text --> A5[parse_check_response(raw)]
        A5 --> A6{defects found?}
        A6 -- yes --> A7[record_flag: merge into ai_flags.json] --> A8[["return kind='flagged'"]]
        A6 -- no --> A9[clear_flag: drop any stale flag] --> A10[["return kind='ok'"]]
    end

    subgraph PARSE["parse_check_response(text)"]
        direction TB
        B1{first line == 'OK'?}
        B1 -- yes --> B2[["return []"]]
        B1 -- no --> B3{first line starts 'DEFECTS'?}
        B3 -- yes --> B4[dash-prefixed lines -> list]
        B4 --> B5{list empty?}
        B5 -- yes --> B6{defects on header line itself?}
        B6 -- yes --> B7[["return [that text]"]]
        B6 -- no --> B8[["raise AiError — no defects named"]]
        B5 -- no --> B9[["return defects list"]]
        B3 -- no --> B10[["raise AiError — unexpected shape"]]
    end

    subgraph RESEND["plan_resend(flagged, drop_to_source)"]
        direction TB
        C1[for each flag key] --> C2[drop_and_site_for(key)]
        C2 -- None --> C3[unmatched: no site in path]
        C2 -- drop, site --> C4{drop in drop_to_source?}
        C4 -- no --> C5[unmatched: not in any queued collection]
        C4 -- yes --> C6[plans[site][source].add(drop)] --> C7[notes[site][drop] = fix_note(defects)]
    end
```

Pseudocode (language-neutral):

    FUNCTION check_one_image(src, out_base, instructions, prompt, model):
        model = model OR model_for("vision")           # resolved BEFORE the call
        key = flag_key(src, out_base)
        TRY:
            raw = check(src, instructions, prompt, model)
            defects = parse_check_response(raw)
        CATCH AiError as exc:
            RETURN {rel: key, kind: "error", defects: [], raw: str(exc)}

        IF defects:
            record_flag(out_base, src, defects, model, raw)
            RETURN {rel: key, kind: "flagged", defects, raw}
        ELSE:
            clear_flag(out_base, src)                    # a fixed image loses its old flag
            RETURN {rel: key, kind: "ok", defects: [], raw}

    FUNCTION parse_check_response(text):
        first_line, rest = split text on first newline
        IF first_line.strip().upper() == "OK": RETURN []
        IF first_line starts with "DEFECTS":
            defects = [line stripped of "- * •" for each non-blank line in rest]
            IF defects is empty:
                IF text after "DEFECTS:" on the SAME line is non-blank:
                    RETURN [that text]
                RAISE AiError("no defects named")
            RETURN defects
        RAISE AiError("unexpected check response shape")

    FUNCTION plan_resend(flagged, drop_to_source):
        FOR EACH (key, defects) IN flagged:
            mapped = drop_and_site_for(key)               # reverse dest_for
            IF mapped is None: unmatched.append((key, "no site in path")); CONTINUE
            (drop, site) = mapped
            source = drop_to_source.get(drop)
            IF source is None: unmatched.append((key, "not in any queued collection")); CONTINUE
            plans[site][source].add(drop)
            notes[site][drop] = fix_note(defects)
        RETURN (plans, notes, unmatched)
