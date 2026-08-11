# Recovery — flow

The image-failure recovery ladder (`recover_image_failed`), cheapest
rung first. See [about](../__about/recovery.md) for the responsibility
and the split history.

```mermaid
flowchart TD
    A[ImageGenFailed arrives] --> B{rung 1: site's native\nRetry button present?}
    B -- clicked --> B1[await_done + extract_image]
    B1 -- image --> OK[[return bytes, t_send]]
    B1 -- ImageGenFailed --> C
    B -- no button --> C

    C[rung 2: paced text retries] --> C1{attempt <= IMAGE_FAILED_RETRY_MAX?}
    C1 -- yes --> C2[interruptible_sleep random RETRY_DELAY_RANGE]
    C2 -- Stop fired --> STOP[[raise ImageGenFailed - worker stops]]
    C2 --> C3[generate_one IMAGE_RETRY_NUDGE]
    C3 -- image --> OK
    C3 -- ImageGenFailed --> C1
    C1 -- spent --> D

    D[rung 3: escalation rounds] --> D1{round per ESCALATION_DELAYS entry}
    D1 -- next round --> D2[interruptible_sleep random range - minutes]
    D2 -- Stop fired --> STOP
    D2 --> D3[refresh page + new_chat]
    D3 --> D4[generate_one WHOLE prompt,\nre-attaching input images]
    D4 -- image --> OK
    D4 -- ImageGenFailed --> D1
    D1 -- spent --> E[[RECOVERY EXHAUSTED - raise, site stops,\nfiles on disk resume the next run]]
```

Notes:

- Only `ImageGenFailed` is caught per rung — a quota (`TerminalState`)
  or refusal (`ItemRefused`) surfacing mid-recovery propagates loudly
  to the runner's own handlers, exactly as on a first attempt.
- `interruptible_sleep` wakes every 0.5 s to honour Stop; True =
  Stop cut the wait — the ladder abandons recovery the same way as
  exhaustion (the raise), never half-continues.
- Rung 3 is the ONLY rung that re-attaches "← ref" input images: the
  earlier rungs stay in the same chat where the image(s) already sit;
  the new session has no history.
