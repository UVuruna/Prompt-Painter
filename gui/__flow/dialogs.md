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

## AiSheetDialog — retired (faza 4)

The two-phase request → questions → sheet flow moved into the
persistent [Sheet Generator Panel](../__about/sheetgen_panel.md)
(wizard ① Zahtev → ② Pitanja → ③ Draft & Save) — same engine
calls, editable parser-revalidated draft instead of the DocWindow
detour.
