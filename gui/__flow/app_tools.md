# Tool Jobs Mixin — Flow

**About:** [description](../__about/app_tools.md)

## Algorithm — `_run_tool_job` (one standalone tool's whole run)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A(["worker thread starts"]) --> B["FOR EACH file, in order"]
    B --> C{"stop requested?"}
    C -- yes --> Z["break — STOPPED, counts logged"]
    B --> D{"paused?<br/>(wait_while_paused, stop wins)"}
    D -- stop won --> Z
    D -- proceed --> E["backup ORIGINAL (JobTemp)"]
    E --> F["run engine func(src, log)"]
    F --> G{"status?"}
    G -- "done (file rewritten)" --> H["measure BEFORE→AFTER<br/>emit item_done + metric"]
    G -- "nothing/unclear/FAILED" --> I["drop the no-op backup<br/>emit item_refused"]
    H --> B
    I --> B
    B -->|"all files done"| J["emit sheet_done, log summary"]
    J --> K["finally: post __tool_done__ (ALWAYS)"]
```

## Pseudocode — the AI checker's two-input matching (F6)

```
FUNCTION run_ai_check_job(folder, files, out_base, sheets_path=None):
    prune_stale_flags(out_base)
    IF sheets_path is None:
        pairs = [(file, prompt=None) for file in files]     # quality-only
    ELSE:
        drop_to_prompt = sheet_prompt_map(sheets_path)        # walks a folder too
        pairs = []
        FOR src IN files:
            drop = reverse-lookup src's drop path (dest_for reverse)
            IF drop in drop_to_prompt:
                pairs.append((src, drop_to_prompt[drop]))     # prompt-aware check
            ELSE:
                unmatched += 1                                 # logged, not silent
    FOR (src, prompt) IN pairs, checking stop/pause between each:
        result = ai.check_one_image(src, prompt)
        emit item_flagged / item_ok / item_error accordingly
    emit sheet_done
```

Both `_run_tool_job` and `_run_ai_check_job` check `stop_event`/
`pause_event` at the SAME between-items boundary `run_sheet` itself
uses — the in-flight image/vision call always finishes first, and a
Stop wins over a pending Pause via `wait_while_paused`'s own contract.
