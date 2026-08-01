# Run Loop — Flow

**About:** [description](../__about/runner.md)

## Algorithm — per-item handling inside `run_sheet`

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A([next queued item]) --> B{should_stop / paused?}
    B -- stop --> Z1[["loop ends — stopped_why set"]]
    B -- no --> C[resolve input image if any;
    missing file -> loud skip, continue]
    C --> D[generate_one: submit + await_done + extract_image]
    D --> E{exception?}
    E -- none --> N
    E -- ItemRefused --> F{safer_retry on and
    preamble for category?}
    F -- yes --> F1[resend once with preamble] --> F2{refused again?}
    F2 -- yes --> S1[["skip_reason = refused"]]
    F2 -- no --> N
    F -- no --> S1
    E -- NoImage had_text=True --> S2[["skip_reason = no image (text) — never nudge"]]
    E -- NoImage had_text=False --> G{continue_nudge on?}
    G -- yes --> G1[send CONTINUE_NUDGE once] --> G2{NoImage again?}
    G2 -- yes --> S2
    G2 -- no --> N
    G -- no --> S2
    E -- ModelDegraded --> H[on_degrade choice]
    H -- continue --> S3[["skip_reason = model degraded"]]
    H -- wait --> H1[["raise TerminalState — auto-restart at reset"]]
    E -- ImageGenFailed --> I{image_failed_retry on?}
    I -- no --> I1[["propagate — stops the site"]]
    I -- yes --> I2[_recover_image_failed ladder:
    retry button -> paced retry text
    -> escalation refresh+new-session]
    I2 -- recovered --> N
    I2 -- ItemRefused mid-ladder --> F
    I2 -- exhausted --> I3[["propagate ImageGenFailed — stops the site"]]

    N[data bytes obtained] --> J{sha1 == last_saved_digest?}
    J -- yes --> J1[one fresh re-submit] --> J2{still duplicate?}
    J2 -- yes --> S4[["skip_reason = duplicate persisted"]]
    J2 -- no --> K
    J -- no --> K[save at dest / next _vN version]
    K --> L[post_save hook: bg/crop/upscale, loud but never fatal]
    L --> M[emit item_progress; pause; emit item_done]
    M --> O{degrade banner up now?}
    O -- yes --> H
    O -- no --> A

    S1 --> P[emit item_refused; log to report] --> A
    S2 --> P
    S3 --> P
    S4 --> P
```

Pseudocode (language-neutral):

    FUNCTION run_sheet(sheet, driver, out_base, site_key, ...):
        queue = items not yet on disk (unattended) OR the ticked `only` set
        FOR EACH item IN queue:
            IF should_stop() OR wait_while_paused(...): BREAK

            input_path = resolve item.input_image relative to sheet folder
                         (missing file -> loud skip, CONTINUE)

            TRY:
                (data, t_send) = generate_one(item.prompt + suffix, input_path)
            CATCH ItemRefused AS exc:
                (data, t_send) = try_safer_retry(exc) OR skip_reason = "refused"
            CATCH NoImage AS exc:
                IF exc.had_text: skip_reason = "no image (text)"     # never nudge
                ELSE IF continue_nudge:
                    TRY (data, t_send) = generate_one(CONTINUE_NUDGE)
                    CATCH NoImage: skip_reason = "no image after nudge"
                ELSE: skip_reason = "no image"
            CATCH ModelDegraded AS exc:
                choice = on_degrade(exc.retry_after_s) OR "wait"
                IF choice == "continue": skip_reason = "model degraded"
                ELSE: RAISE TerminalState(exc)                       # auto-restart
            CATCH ImageGenFailed AS exc:
                IF NOT image_failed_retry: RAISE                     # stops the site
                TRY (data, t_send) = recover_image_failed_ladder(exc)
                CATCH ItemRefused nested: same handling as ItemRefused above

            IF skip_reason: report + emit item_refused; pause; CONTINUE

            IF sha1(data) == last_saved_digest:                      # duplicate guard
                TRY (data, t_send) = generate_one(item.prompt + suffix) ONCE more
                IF still duplicate: skip_reason = "duplicate persisted"; CONTINUE

            rel = version_dest[item.drop_path] OR dest_for(item.drop_path, site_key)
            WRITE data TO out_base / rel
            actions = post_save(dest) IF post_save ELSE []            # loud, never fatal
            EMIT item_progress(rel, gen_s, actions)
            pause(timing)                                             # paced, Stop-aware
            EMIT item_done(rel, gen_s, over_s, actions)

            IF degrade_banner_probe() is up AND not degrade_handled:
                same on_degrade choice as ModelDegraded above
