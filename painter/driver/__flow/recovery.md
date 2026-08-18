# Driver Recovery — Flow

**About:** [description](../__about/recovery.md)

## Algorithm — one rung at a time

Each box below is a SEPARATE public call. This module never decides how
far to climb: [Recovery Ladder](../../__about/recovery.md) owns that
policy, and calls one rung at a time.

```mermaid
flowchart TB
    R0[["the runner met ImageGenFailed / SendVanished /
    SendNotConfirmed"]] --> R1{site ships an
    error-Retry button?}
    R1 -- yes, present --> R2[click_error_retry: click it
    -> True]
    R1 -- absent / site has none --> R3[["False — a normal branch,
    never loud"]]
    R2 --> R9[["back to await_done"]]
    R3 --> R4[_retry_send: re-send the last
    confirmed prompt, ONE try]
    R4 --> R9
    R4 -- still failing --> R5[refresh: page.reload,
    wait for the composer back]
    R5 -- composer late --> R6[ONE more reload,
    doubled budget]
    R6 -- still gone --> R7[["raise — loud"]]
    R5 --> R9
    R6 --> R9
    R5 -- escalation round --> R8[new_chat: click the sidebar
    control, wait for a fresh composer,
    re-anchor the baseline to nothing]
    R8 --> R9
```

Pseudocode (language-neutral):

    FUNCTION click_error_retry(log) -> bool:
        IF the site declares no image_error_retry_button: RETURN False
        IF the button is not present:                     RETURN False
        click it
        RETURN True                       # never loud — absence is normal

    FUNCTION refresh(log):
        page.reload()
        wait for the composer up to the selector timeout
        IF the composer did not come back:
            page.reload() ONCE more with a DOUBLED budget
            IF still gone: RAISE                # loud
        # the login lives in the profile on disk — nothing to re-enter

    FUNCTION new_chat(log):
        click the sidebar's new-chat control
        wait for the fresh composer
        baseline = None            # a fresh conversation restarts turn numbering

    FUNCTION _retry_send():
        re-send the LAST CONFIRMED prompt — the single try the
        SendVanished / SendNotConfirmed handler is allowed
