# Gemini REST Client — Flow

**About:** [description](../__about/client.md)

## Algorithm — `_send_request`'s retry/pace/classification shell

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A([_send_request: request, label]) --> B[attempt = 1]
    B --> C[_pace: sleep until AI_CALL_PAUSE_S
    since the last call]
    C --> D[urlopen request]
    D -- HTTPError --> E[parse body once: message, retry_s]
    E --> F{429 AND free-tier-exhausted signal?}
    F -- yes --> G[["raise PaidFeatureRequired — never retried"]]
    F -- no --> H{status in AI_TRANSIENT_STATUS
    AND attempt < AI_RETRY_MAX?}
    H -- no --> I[["raise AiError(status=code)"]]
    H -- yes --> J[wait = server retry_s for 429,
    else AI_RETRY_BACKOFF_S]
    J --> K[log retry, sleep wait] --> L[attempt += 1] --> C
    D -- URLError --> M[["raise AiError — unreachable"]]
    D -- 200 OK --> N{JSON-decodes?}
    N -- no --> O[["raise AiError — non-JSON body"]]
    N -- yes --> P[["return parsed dict"]]
```

Pseudocode (language-neutral):

    FUNCTION _send_request(request, label):
        FOR attempt IN 1..AI_RETRY_MAX:
            pace()                                    # keep calls AI_CALL_PAUSE_S apart
            TRY:
                raw = urlopen(request)
            CATCH HTTPError AS exc:
                (message, retry_s) = parse_http_error_body(exc)   # read body ONCE
                IF exc.code == 429 AND is_paid_quota_error(message):
                    RAISE PaidFeatureRequired(message)            # permanent, first try
                IF exc.code NOT IN TRANSIENT_STATUS OR attempt == AI_RETRY_MAX:
                    RAISE AiError(message, status=exc.code)       # permanent or exhausted
                wait = retry_s (429, capped) ELSE AI_RETRY_BACKOFF_S (503/500)
                LOG retry; SLEEP(wait); CONTINUE
            CATCH URLError AS exc:
                RAISE AiError("unreachable: " + exc.reason)
            RETURN json_decode(raw)                    # loud AiError on malformed JSON
        # unreachable — the final attempt above always raises or returns

    FUNCTION model_for(purpose):
        override = settings.json["models"][purpose]     # per-purpose GUI override
        RETURN override IF non-blank ELSE hardcoded fallback constant for purpose

    FUNCTION recommend_model(models, purpose):
        capable = capable_models(models, purpose)        # name/method filter
        FOR EACH ranked_substring IN MODEL_PURPOSE_RANKING[purpose]:
            FOR EACH model IN capable:
                IF ranked_substring IN model.name: RETURN model.name
        RETURN newest_by_name(capable) IF capable ELSE None
