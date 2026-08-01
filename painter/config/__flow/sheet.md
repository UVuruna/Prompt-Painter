# Sheet — Flow

**About:** [description](../__about/sheet.md)

## Structure

```mermaid
flowchart TB
    A[sheet.py] --> B[THE SHEET CONTRACT<br/>IMAGE_EXTENSIONS, SKIP_MARKER_PATTERN]
    A --> C[MULTI-FILE SELECTION BASE<br/>selection_base_and_rels]
    A --> D[IMAGE / MD FILE ENUMERATORS<br/>TOOL_IMAGE_EXTENSIONS, iter_images, iter_md_files]
```

## Algorithm — `selection_base_and_rels`

```mermaid
flowchart TB
    A[list of file paths] --> B{empty?}
    B -- yes --> C[raise ValueError]
    B -- no --> D{exactly one file?}
    D -- yes --> E[base = its parent folder]
    D -- no --> F[base = common ancestor of all parents]
    E --> G[rel = each file's path, relative to base, POSIX]
    F --> G
    G --> H[(base, list of rel)]
```

Pseudocode:

    FUNCTION selection_base_and_rels(paths):
        files = [Path(p) for p in paths]
        IF files is empty: raise ValueError
        IF len(files) == 1:
            base = files[0].parent
        ELSE:
            base = common_path(f.parent for f in files)
        rels = [f.relative_to(base).as_posix() for f in files]
        RETURN base, rels

`iter_images`/`iter_md_files` are a single `rglob` walk each, sorted —
no branching worth a diagram beyond "recursive glob, filter by
extension, sort".
