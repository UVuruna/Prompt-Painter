# Driver Protocol — Flow

**About:** [description](../__about/protocol.md)

## Algorithm — one prompt in, provably sent

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph SUBMIT["submit_prompt(prompt) / submit_with_image(image, prompt)"]
        direction TB
        S0[_ensure_ready: known-stuck button
        refreshes at once, else wait up to
        busy_stuck_timeout_s then refresh] --> S1[capture_baseline:
        turn_count, last_img_src]
        S1 --> S2{submit_with_image?}
        S2 -- yes --> S3[_attach_image: walk '+' menu,
        set file, wait for preview]
        S2 -- no --> S4
        S3 --> S4[_type_into_box: clear if non-empty,
        insert prompt, VERIFY it landed]
        S4 --> S5[_click_send]
        S5 --> S6{SelectorRot on send button?}
        S6 -- yes, first miss --> S7[reload page, reattach image
        if any, retype, retry ONCE]
        S7 --> S5
        S6 -- no / second miss --> S8[click send]
        S8 --> S9[_confirm_sent: poll for
        composer empty AND our text
        as newest user turn]
        S9 -- not confirmed by halfway --> S10[retry: click+Enter] --> S9
        S9 -- confirmed --> S11[["submitted"]]
        S9 -- timeout --> S12[["raise SendNotConfirmed"]]
    end
```

Pseudocode (language-neutral):

    FUNCTION submit_prompt(prompt):
        ensure_ready()                     # wait out a genuinely busy composer
        baseline = capture_baseline()      # turn_count, last_img_src, user_turn_count
        type_into_box(prompt)              # clear-if-non-empty, insert, VERIFY
        click_send(prompt)                 # ONE reload-recovery retry on SelectorRot
        confirm_sent(prompt)               # poll: composer empty + our text is
                                           # the newest user turn; one mid-window retry
        sent_head = prompt's normalized 60-char head   # the F1b anchor
        sent_norm = prompt's full normalized text      # the TEXT-first anchor

The wait half that judges the result against this submit's `Baseline`
lives in [wait](wait.md).
