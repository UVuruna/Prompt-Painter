# Modal Dialogs — Flow

**About:** [description](../__about/dialogs.md)

## Layout — AiKeyWizard (modal)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph WIN["AiKeyWizard (grab_set — fully modal)"]
        H["Header: 'Get a FREE Gemini API key' + subtitle"]
        S1["Step 1: 'Open aistudio.google.com' button"]
        S234["Steps 2-4: sign in / create key / paste — static text"]
        ENTRY["Key entry"]
        STATUS["Status label (ok=green / err=red / info=neutral)"]
        BTNS["Save key · Test key · Cancel"]
    end
    H --> S1 --> S234 --> ENTRY --> STATUS --> BTNS
```

## Layout — AiSheetDialog (non-modal, two phases)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph WIN["AiSheetDialog (THEME_TOPLEVELS-registered)"]
        REQ["Phase 1 box: header + hint + multi-line request Text"]
        POLL["Phase 2 box (hidden until questions arrive): one row per clarifying question — label + entry"]
        STATUS["Status label"]
        BTNS["'Ask questions' / 'Generate sheet' (same button, text swaps) · Cancel"]
    end
    REQ --> POLL --> STATUS --> BTNS
```

## Algorithm — shared worker-queue poll loop (`_AiDialog`)

```
init_ai_queue():  q = Queue();  poll_job = None

arm_poll():  poll_job = after(AI_POLL_MS, poll)

poll():
    poll_job = None
    if window destroyed: return          # closed mid-work — result is moot
    if a message is queued: on_message(message)   # subclass-specific
    else: arm_poll()                     # try again next tick
```

Every worker thread ONLY calls `self._q.put(...)` — it never touches
a Tk widget; only `poll()`'s `on_message` runs on the main thread.

## Algorithm — AiKeyWizard "Test key"

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TD
    A["Test key clicked"] --> B{"key pasted?"}
    B -->|no| C["show red error status"]
    B -->|yes| D["disable Test button · status = 'testing — one tiny API call …'"]
    D --> E["worker thread: ai.generate_text(TEST_PROMPT, key=key)"]
    E -->|success| F["queue: ('ok', 'OK — the key works (...)')"]
    E -->|ai.AiError| G["queue: ('err', str(exc))"]
    D --> H["arm_poll()"]
    H --> I["on_message((kind, text)): re-enable Test button, colour+set the status label"]
```

## Algorithm — AiSheetDialog two-call flow

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TD
    A["'Ask questions' clicked"] --> B{"request text non-empty?"}
    B -->|no| C["error dialog — return"]
    B -->|yes| D["log request to main window · busy · worker thread"]
    D --> E["contract = ai.contract_text(); questions = ai.ask_questions(request, contract)"]
    E --> F["queue: ('questions', contract, questions)  |  ('error', msg)"]
    F --> G{"on_message"}
    G -->|error| H["log + idle status = error text"]
    G -->|questions non-empty| I["show one entry row per question · button becomes 'Generate sheet'"]
    G -->|questions empty| J["skip straight to _generate() — nothing to ask"]
    I --> K["'Generate sheet' clicked"]
    K --> L["busy · worker thread: ai.generate_sheet(request, questions, answers, contract, tmp_dir, log)"]
    L --> M["queue: ('sheet', md, problems, theme)  |  ('error', msg)"]
    M --> N["_finish(md, problems, theme)"]
    N --> O{"problems?"}
    O -->|yes| P["log each problem · status = 'still fails contract — opened for manual fixing, NOT loaded' · open DocWindow(md) · dialog stays open"]
    O -->|no| Q["path = ai.save_sheet(md, theme, SHEETS_DIR) · add_generated_sheet(path) · log · close dialog"]
```
