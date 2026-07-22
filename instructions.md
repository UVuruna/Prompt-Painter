# How to Write a Prompt Sheet — the PromptPainter Contract

Audience: any author of a prompt sheet — a person or an agent.
Follow these rules and PromptPainter will read your sheet, generate
every image on Gemini/ChatGPT, name the files exactly as you wrote
them, and file them into the right folders. Deviate and the tool
will tell you loudly what is wrong (or, for old habits, quietly do
its best — see [Legacy forms](#legacy-forms)).

## The one-minute version

````markdown
# My Theme Name — what this sheet generates

**The First Image — short description** →
`assets/weekday/my_theme/primary/First_Image.png`

```
The full generation prompt, exactly as it must be pasted.
```

**The Second Image** → `assets/weekday/my_theme/primary/Second_Image.png`

```
Another prompt.
```
````

That is a complete, valid sheet. Everything below is detail.

## The rules

### 1. One theme = one file; the H1 names it
The first `# Heading` is the THEME NAME. A file without an H1 is
rejected outright.

### 2. The entry: bold title, arrow, backticked path
```markdown
**Title of the image** → `assets/emblem/mood/Glory.png`
```
- The `→` arrow line carries the OUTPUT PATH — the tool names and
  files images itself, no renaming ever happens afterwards.
- Write the FULL, SITE-AGNOSTIC assets path:
  `assets/<folders...>/<File>.png`. The tool adds the generator as a
  FILENAME SUFFIX (`_gpt` / `_gem` / `_api`), so the output tree
  mirrors the DOMY assets tree exactly:
  `assets/emblem/mood/Glory.png` → `out/emblem/mood/Glory_gem.png`
  — and a finished collection copies straight into `assets/`.
- The path must end in `.png` and be UNIQUE within the sheet.
- Long titles and paths may wrap across lines; plain text may sit
  between the bold title and the arrow; the title may contain
  single backticks (`` `#8000FF` ``).
- A bold title ending with `:` is prose, never an entry
  (`**Drop paths:** ...`).

### 3. The prompt: the FIRST fenced code block after the entry
````markdown
```
The prompt, copied byte-identical into the chat box.
```
````
One block per entry. Notes may sit between the entry line and the
block. The tool appends its own site rules (background, no
reflections) AFTER your prompt — do not write those yourself unless
the image needs something unusual.

### 3b. What every prompt MUST state explicitly (owner 2026-07-22)

The tool NEVER guesses what the image should look like from your
wording — it once inferred the aspect ratio from keywords, and "a
tall lotus-tipped sceptre" inside a ROUND-medallion prompt turned
the whole image portrait. Descriptions of ELEMENTS (a tall sceptre,
wide wings, a long staff) must never be able to change the WHOLE
image. So every prompt states, in its own text, unambiguously:

- **ASPECT RATIO** — exact and about the WHOLE image, e.g.
  "ASPECT RATIO exactly 1:1 — a perfect square image" or
  "ASPECT RATIO tall portrait, around 2:3 — clearly taller than
  wide". Never rely on shape words ("round", "tall window") to
  imply it.
- **SHAPE / FRAMING** — what the image IS: rondel, medallion,
  lancet window, plate, badge... and whether the shape is the frame.
- **BACKGROUND** — only when the image needs something OTHER than
  the run's default (the tool appends the per-site background rule
  from the GUI dropdown; writing a conflicting one confuses the
  model).
- Anything else the image depends on (palette, lettering bans,
  symmetry...) — if it matters, write it; the tool adds nothing
  beyond the background/site rules above.

### 4. Notes and prose
*(Italic paragraphs)* and any paragraph that does not carry an
entry's path are ignored — write as much context as you like.

### 5. Skip markers are ADVICE
`REUSE`, `SUPERSEDED`, `DO NOT GENERATE` (inside `**bold**`):
- on an entry that still has a path + prompt → the entry LOADS but
  is UNTICKED by default in the tool's selection window (the
  operator can still tick it);
- as a standalone bold note, or in a section heading → advises
  every entry until the next heading;
- on an entry with NO prompt → the entry is just listed (there is
  nothing to generate).

### 6. What gets rejected loudly (fix the sheet, not the tool)
- no `# H1` theme heading;
- an entry heading with no prompt block after it;
- a drop path that escapes the output folder (`../...`);
- two entries writing the same path.

<a id="legacy-forms"></a>
## Legacy forms (accepted, but do not write new sheets this way)

Older sheets are read best-effort:
- `### Image Name (`file.png`)` — filename in the heading;
- a whole paragraph of exactly `**Name** — `file.png``;
- a bare `**Name**` under a section heading that carries a
  backticked drop dir (`## SIGN look (`assets/.../sign/`)`).

Their quirks (reuse pointers, duplicate or `../` paths, unpaired
mentions) are silently ignored. NEW sheets must use the canonical
arrow form — it is the only one with loud error checking.

## Checklist before handing the sheet over

- [ ] `# H1` theme name at the top
- [ ] every image: `**Title** → \`assets/<folders>/.../File.png\``
      + one fenced prompt block
- [ ] every path unique, `.png`, full `assets/` form (site-agnostic)
- [ ] every prompt states its ASPECT RATIO and SHAPE explicitly
      (rule 3b — the tool never infers them)
- [ ] REUSE / not-approved entries marked in bold
- [ ] run `python main.py "your_sheet.md" --dry-run` (or the GUI's
      "Check sheets") — zero problems reported
