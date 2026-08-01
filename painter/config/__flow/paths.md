# Paths — Flow

**About:** [description](../__about/paths.md)

## Structure

```mermaid
flowchart TB
    A[paths.py] --> B[PROJECT ROOT]
    A --> C[CDP ATTACHMENT / CHROME LAUNCH]
    A --> D[OUTPUT LAYOUT — dest_for / versioned_dest_for]
    A --> E[SETTINGS PERSISTENCE]
```

## Algorithm — `dest_for`

```mermaid
flowchart TB
    A[drop_path, site_key] --> B[split drop_path on '/']
    B --> C{parts0 == 'assets'<br/>AND len >= 3?}
    C -- yes --> D[take the filename, split stem/ext]
    D --> E[insert SITE_FILE_SUFFIX before the extension]
    E --> F[rejoin parts 1..-1 + new name]
    C -- no --> G["legacy: site_key/drop_path"]
    F --> H[(relative save path)]
    G --> H
```

Pseudocode:

    FUNCTION dest_for(drop_path, site_key):
        parts = drop_path.split("/")
        suffix = SITE_FILE_SUFFIX[site_key]      # KeyError if unregistered
        IF parts[0] == "assets" AND len(parts) >= 3:
            name = parts[-1]
            stem, ext = split on last "."
            name = f"{stem}{suffix}.{ext}"        # suffix ALWAYS terminal
            RETURN "/".join(parts[1:-1] + [name])
        RETURN "/".join([site_key, drop_path])    # legacy non-assets drop

## Algorithm — `versioned_dest_for`

```mermaid
flowchart TB
    A[drop_path, site_key, out_base] --> B[rel = dest_for drop_path, site_key]
    B --> C[split rel into folder / stem / ext]
    C --> D[strip the generator suffix from stem -> base]
    D --> E[build regex: base_v-digits-tail-.ext]
    E --> F[scan out_base/folder for matching siblings]
    F --> G[last = max over matches, 1 if none/bare '_v']
    G --> H["versioned name = base_v(last+1)+tail+.ext"]
    H --> I[(folder/versioned name)]
```

Pseudocode (language-neutral — the owner's rotation rule):

    FUNCTION versioned_dest_for(drop_path, site_key, out_base):
        rel = dest_for(drop_path, site_key)
        folder, name = split rel on last "/"
        stem, ext = split name on last "."          # legacy: no ext
        suffix = SITE_FILE_SUFFIX[site_key]
        tail = suffix IF stem ends with suffix ELSE ""
        base = stem WITHOUT the trailing tail

        pattern = base + "_v" + (digits, optional) + tail + ("." + ext)?

        last = 1                                     # canonical file = v1
        FOR EACH file IN (out_base / folder):
            IF file matches pattern:
                last = MAX(last, digits OR 1)         # bare "_v" counts as 1
        RETURN folder / (base + "_v" + (last + 1) + tail + "." + ext)

Gaps in the existing `_vN` siblings never matter — only the highest
found number decides the next one. The owner's irregular `_v`/`_v1`
forms both parse as version 1, matching DOMY's own rotation
convention.
