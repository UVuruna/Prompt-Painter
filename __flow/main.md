# Main (Entry Point) — Flow

**About:** [description](../__about/main.md)

## Algorithm

```mermaid
flowchart TB
    A[python main.py ...] --> B{sheet args given?}
    B -- no --> C[open the GUI]
    B -- yes --> D[parse + report each sheet]
    D --> E{--dry-run?}
    E -- yes --> F[exit 0 clean / 2 if any broken]
    E -- no --> G{usable sheets AND --site given?}
    G -- no --> H[exit 2: error]
    G -- yes --> I[reject sheets living inside --out]
    I --> J[build the composed post_save hook<br/>bg + crop + upscale flags]
    J --> K{deps missing for a requested step?}
    K -- yes --> L[exit 2: error]
    K -- no --> M[ensure_chrome over CDP]
    M --> N{Chrome just launched?}
    N -- yes --> O[exit 0: log in, rerun]
    N -- no, attached --> P[attach SiteDriver]
    P --> Q[FOR EACH sheet in order: run_sheet]
    Q --> R{new_chat policy fires<br/>and more sheets remain?}
    R -- yes --> S[driver.new_chat, continue]
    R -- no --> Q
    Q --> T[TerminalState / DriverError / KeyboardInterrupt?]
    T -- TerminalState --> U[exit 3: quota, resume later]
    T -- DriverError --> V[exit 1: rerun once fixed]
    T -- Ctrl-C --> W[exit 130: progress saved]
    T -- none --> X[exit 0 / 2 if any sheet was broken]
```

Pseudocode (language-neutral):

    parse CLI args
    IF no sheet arguments:
        open GUI, return 0

    FOR EACH sheet argument:
        TRY parse_sheet(path)
        EXCEPT unreadable/contract error: report, mark broken, skip
        ELSE: print report; IF sheet has problems: mark broken, skip
              ELSE: keep it

    IF --dry-run: return (2 if any broken else 0)
    IF no usable sheets OR no --site: print error, return 2
    IF any sheet's source path resolves inside --out: print error, return 2

    build post_save hook FROM (--no-bgfix, --no-crop, --upscale)
    IF the hook reports a missing dependency: print error, return 2

    resolve pause timing FROM --pause (fixed or random range)
    resolve prompt suffix FROM (--site, --background)

    ensure a debuggable Chrome is running (launch with the project
        profile if none answers)
    IF Chrome was just launched: print "log in, rerun", return 0

    attach SiteDriver over CDP
    total = 0
    FOR EACH sheet, in the given order:
        generated = run_sheet(sheet, driver, ...)
        total += generated
        IF new_chat policy says so AND more sheets remain:
            driver.new_chat()   # failure here is logged, never fatal
    print totals
    return (2 if any sheet was broken else 0)

    ON TerminalState (quota): return 3
    ON DriverError: return 1
    ON KeyboardInterrupt: return 130
    FINALLY: driver.close()
