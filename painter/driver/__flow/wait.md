# Driver Wait — Flow

**About:** [description](../__about/wait.md)

## Algorithm — the done edge and the bytes

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph AWAIT["await_done()"]
        direction TB
        A0[poll loop, bounded by
        generation_timeout_s] --> A1{new assistant turn
        beyond baseline?}
        A1 -- no --> A2{busy signal ever appeared?}
        A2 -- no, past busy_appear_timeout_s --> A3[["raise NoImage(had_text=False)"]]
        A2 -- yes, still waiting --> A0
        A1 -- yes --> A4{turn holds a loaded
        image with a NEW src?}
        A4 -- yes --> A5[["done — extract next"]]
        A4 -- no --> A6[scan turn text]
        A6 --> A7{degrade banner up?}
        A7 -- yes --> A8[["raise ModelDegraded"]]
        A7 -- no --> A9{image-failed marker?}
        A9 -- yes --> A10[["raise ImageGenFailed"]]
        A9 -- no --> A11{quota / refusal marker?}
        A11 -- quota --> A12[["raise TerminalState"]]
        A11 -- refusal --> A13[["raise ItemRefused(category)"]]
        A11 -- no match --> A14{text present and
        not busy, settled?}
        A14 -- yes --> A15[["raise NoImage(had_text=True)"]]
        A14 -- no --> A0
    end

    subgraph EXTRACT["extract_image()"]
        direction TB
        X0[locate the new turn's loaded
        image, src != baseline] --> X1[canvas drawImage +
        toDataURL in-page]
        X1 -- CSP blocks fetch of blob --> X1
        X1 -- canvas fails --> X2[fallback: fetch + FileReader]
        X2 -- both in-page paths fail --> X4[_fetch_via_context:
        the browser CONTEXT's request API,
        outside the page — no CORS]
        X2 --> X3[["return decoded bytes"]]
        X1 --> X3
        X4 --> X3
    end

    AWAIT --> EXTRACT
```

The verdicts the poll loop reaches (`ModelDegraded`, `ImageGenFailed`,
`TerminalState`, `ItemRefused`) are made by
[classify](classify.md), not here.

Pseudocode (language-neutral):

    FUNCTION await_done():
        baseline = the captured Baseline
        WHILE elapsed < generation_timeout_s:
            # F1b anchor (owner 2026-08-04): ok / vanished / unavailable
            anchor = does the newest USER turn still read as OUR prompt
                     (head present, then text agrees for ANCHOR_VERIFY_CHARS)?
            IF anchor == vanished FOR >= text_settle_s:
                RAISE SendVanished          # site dropped our message —
                                            # runner re-sends the item's OWN prompt
            IF anchor == ok:
                turn = last assistant turn IF it FOLLOWS our user turn
                       in the DOM ELSE None          # count IGNORED (virtualization)
            ELSE:  # unavailable — no user_turn selector / nothing confirmed
                turn = last assistant turn IF conversation grew past baseline ELSE None
            IF turn has a loaded image with src != baseline.last_img_src:
                busy_known_stuck = busy               # a still-set button IS stuck
                RETURN                                # done
            IF turn has text:
                IF degrade_banner up:               RAISE ModelDegraded
                IF text matches image-failed marker: RAISE ImageGenFailed
                IF text matches quota marker:        RAISE TerminalState
                IF text matches refusal marker:      RAISE ItemRefused(category)
                IF text stands alone (not busy) for >= text_settle_s:
                    RAISE NoImage(had_text=True)     # loud skip, never nudge
            ELSE IF not vanished AND nothing new AND busy never appeared
                    past busy_appear_timeout_s:
                RAISE NoImage(had_text=False)        # the one nudge-eligible case
            SLEEP poll_interval
        RAISE GenerationTimeout

    FUNCTION extract_image():
        WHILE elapsed < image_ready_timeout_s:
            img = the new turn's loaded image, src != baseline.last_img_src
            IF img found: BREAK
            check the turn's text for degrade/quota/refusal markers
            SLEEP poll_interval
        TRY canvas drawImage + toDataURL (works even under blob: CSP)
        EXCEPT: fetch(src) + FileReader as fallback
        EXCEPT: the browser CONTEXT's request API (cookies, no CORS)
        RETURN decoded bytes
