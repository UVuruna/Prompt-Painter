# Job Temp / Restore — Flow

**About:** [description](../__about/jobtemp.md)

## Algorithm

```mermaid
flowchart TB
    subgraph PATH["_path_for(rel, step) — the ONE path rule"]
        direction TB
        P0{step is None?}
        P0 -- yes --> P1["root/rel — byte-for-byte legacy path"]
        P0 -- no --> P2["root/__steps__/step/rel — namespaced"]
    end

    subgraph BACKUP["backup(src, rel, step)"]
        direction TB
        B1[resolve dest via _path_for] --> B2[copy2 src -> dest]
        B2 --> B3[record size in _sizes]
    end

    subgraph RESTORE_ALL["restore_all()"]
        direction TB
        R1[walk every file under root] --> R2{under __steps__ ?}
        R2 -- yes --> R3[skip — never touch named-step data]
        R2 -- no --> R4[copy backup back over folder/rel]
    end

    PATH --> BACKUP
    PATH --> RESTORE_ALL
```

Pseudocode (language-neutral):

    FUNCTION _path_for(rel, step):
        IF step IS None:
            RETURN root / rel                       # unchanged legacy path
        RETURN root / "__steps__" / step / rel       # namespaced, never collides

    FUNCTION backup(src, rel, step=None):
        dest = _path_for(rel, step)
        COPY src -> dest (create parent dirs)
        sizes[(rel, step)] = size_of(dest)
        RETURN dest

    FUNCTION restore_all():
        count = 0
        FOR EACH file UNDER root (recursive):
            IF file's first path segment == "__steps__":
                CONTINUE                              # named-step: out of scope
            rel = file's path relative to root
            IF restore_one(rel):
                count += 1
        RETURN count

    FUNCTION measure(kind, before_path, after_path):
        (bw, bh) = size_of(before_path); (aw, ah) = size_of(after_path)
        IF kind == "bg":
            pct = fraction of pixels whose alpha dropped below
                  JOBTEMP_REMOVED_ALPHA between before and after
        ELSE IF kind == "crop":
            pct = (before_area - after_area) / before_area
        ELSE IF kind == "upscale":
            pct = (after_area - before_area) / before_area
        ELSE IF kind == "aspect":
            pct = growth of whichever axis actually changed (w or h)
        RETURN {before: "bw x bh", after: "aw x ah", pct, label}
