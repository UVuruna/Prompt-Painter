# Image Session

**Script:** [Image Session (script)](../imagesession.py)

## Purpose
DECODE ONCE, ENCODE ONCE for a chain of in-place image steps (owner
decree 2026-08-07 — "svaku milisekundu ćemo ako možemo"; root
[CLAUDE.md](../../../../CLAUDE.md) Priority A, Performance).

Every post-save step takes a PATH: it opens the file, transforms the
pixels, writes a full PNG back. Chained, each step therefore re-decodes
what the previous one just encoded. Measured on the owner's 1664x2550
plate, one such round trip costs **1.46 s** (0.08 s decode + 1.38 s
encode) against ~0.3 s of actual pixel work — so a BG → Crop → Aspect
run spent ~2.9 s per image encoding bytes nobody ever looks at.

This module is the buffer between the steps and the disk:

| Function | What it does |
|----------|--------------|
| `load(path)` | the decoded image — from the session when the previous step left one there, else off disk |
| `store(path, img)` | hand the result back; **inside** a session this only marks it dirty, **outside** one it writes immediately |
| `flush()` | write the dirty image, once |
| `invalidate()` | the file changed under us (an external tool wrote it) — drop the cache |
| `session()` | context manager; every `load`/`store` in this thread chains through one image, written on exit |

## Connections
### Uses
- [Config (subfolder)](../config/___config.md) — `PNG_SAVE_KWARGS` (the
  ONE authority for how a PNG is written; this module is the only place
  in the pipeline that still calls `Image.save` for a step's result)
- Pillow, `threading`, `contextlib`

### Used by
- [Postprocess](postprocess.md) — `remove_background`, `crop_transparent`
- [Aspect Filter](aspect.md) — `change_aspect`
- [Upscaler](upscale.md) — the size gate, plus the one `flush()` the
  external binary forces
- [GUI (folder)](../../gui/___gui.md) — `logic._run_pipeline_steps`
  opens the session around the whole chain

## Design Decisions

**Thread-local, never a module global.** ChatGPT and Gemini run as
parallel worker THREADS over their own images. One site's half-finished
image must never be visible to the other, so the session lives in a
`threading.local()`; each thread has its own or none at all.

**Outside a session, behaviour is byte-identical to before.** `load`
reads the file, `store` writes it. That is what keeps the four
standalone tool jobs, the CLI and every existing test unchanged — only a
caller that deliberately opens a session gets the chaining. There was no
flag to add and no caller to migrate.

**At most ONE path is cached.** A pipeline works on a single file at a
time; holding more would only create the chance of serving a stale image
for some other path. `load`/`store` of a different path flush the
previous one first.

**`flush()` before anything else reads the file.** There are exactly two
such readers: a `JobTemp` backup (it COPIES the file) and the
Real-ESRGAN binary (a separate process). Both call it explicitly. This
is the invariant to preserve when adding a step — if your step hands the
path to anything outside this process, flush first.

**The session flushes even when the body raised.** A step that fails
halfway must not silently discard the work of the steps that already
succeeded: the file on disk stays the truth, exactly as when each step
wrote for itself.

**What this does NOT do.** With `keep_all_steps` on (the default) the
intermediate bytes are the FEATURE — each step's pre-state is a real
restore point on disk — so the runner flushes before each backup and the
encode count is unchanged; only the redundant decodes go. With that
toggle off, N steps collapse to ONE encode. The win is therefore real
but conditional, and this is the honest place to say so.
