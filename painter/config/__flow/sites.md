# Sites Config — Flow

**About:** [description](../__about/sites.md)

## Structure

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A[sites.py] --> B[TIMING]
    B --> B1[Timing dataclass, TIMING instance]
    B --> B2[PAUSE_POLL_INTERVAL_S, MIN_IMAGE_PX, SEND_RELOAD_RECOVERY]
    A --> C[REFUSAL SCENARIO CATEGORIES]
    C --> C1[REFUSAL_SAFETY, REFUSAL_COPYRIGHT]
    A --> D[SITE CONFIG — DOM HOOK SCHEMA]
    D --> D1[SiteConfig frozen dataclass]
    A --> E[SITES — PER-SITE DOM CONFIG + NEW-CHAT POLICY]
    E --> E1["SITES chatgpt"]
    E --> E2["SITES gemini"]
    E --> E3[NEW_CHAT_CHOICES]
```

## `SiteConfig` field groups (nested view)

- identity: `name`, `url`, `url_fragment`, `default_background`
- composer: `prompt_box`, `send_button`, `busy_signal`
- result: `response_container`, `result_image`, `user_turn`
- failure signals: `refusal_markers` (by scenario),
  `quota_text_markers`, `degrade_banner`, `image_failed_text_markers`,
  `image_error_retry_button`
- navigation: `new_chat`
- image attach: `attach_menu_path`, `file_input`, `attach_preview`

Every tuple field is a fallback LIST tried in order — the driver never
guesses when none match (root Rule #1).
