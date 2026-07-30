"""``painter.ai`` — the Gemini API client and the AI features'
engine (owner 2026-07-20), one cohesive module per part since the
root Rule #20 package split (2026-07-30):

* [Gemini REST Client](client.md) — the transport, the model
  discovery and the four calls (``generate_text``/``check_image``/
  ``generate_image``/``edit_image``) plus the ``AiError``/``NoKey``/
  ``PaidFeatureRequired`` taxonomy every caller catches.
* [Sheet-Generator Flow](sheet_flow.md) — the owner's #2: questions,
  contract, validate-and-repair, save.
* [Image Checker](checks.md) — the owner's #3: the checker's response
  format, the fix prompt, the per-image driver and the resend plan.
* [Flag Memory](flags.md) — ``<out>/_state/ai_flags.json``, the
  mtime-invalidated record of what a check found.

This ``__init__`` is a PURE re-export shell (the same shape
``painter/config`` and ``gui`` already use), so every existing
``from painter import ai`` / ``ai.generate_image(...)`` call site and
every ``monkeypatch.setattr(ai_module, "edit_image", fake)`` in the
suite keeps working unchanged. The ONE thing that must name a
submodule is a patch of an INTERNAL: ``painter.ai.client._urlopen``
(the HTTP layer) is read by ``_send_request`` from its own module
globals, so it can only be patched there.
"""

from .client import (
    AiError,
    NoKey,
    PaidFeatureRequired,
    api_key,
    capable_models,
    check_image,
    edit_image,
    generate_image,
    generate_text,
    list_models,
    model_for,
    recommend_model,
)
from .sheet_flow import (
    ask_questions,
    contract_text,
    generate_sheet,
    parse_questions,
    qa_block,
    save_sheet,
    slug_for,
    strip_md_fence,
    validate_sheet_md,
)
from .flags import (
    clear_flag,
    clear_flag_keys,
    flag_file,
    flag_key,
    flags_path,
    load_flags,
    prune_stale_flags,
    record_flag,
    save_flags,
)
from .checks import (
    build_fix_prompt,
    check_one_image,
    drop_and_site_for,
    fix_note,
    parse_check_response,
    plan_resend,
)

__all__ = [
    "AiError", "NoKey", "PaidFeatureRequired",
    "api_key", "capable_models", "check_image", "edit_image",
    "generate_image", "generate_text", "list_models", "model_for",
    "recommend_model",
    "ask_questions", "contract_text", "generate_sheet",
    "parse_questions", "qa_block", "save_sheet", "slug_for",
    "strip_md_fence", "validate_sheet_md",
    "clear_flag", "clear_flag_keys", "flag_file", "flag_key",
    "flags_path", "load_flags", "prune_stale_flags", "record_flag",
    "save_flags",
    "build_fix_prompt", "check_one_image", "drop_and_site_for",
    "fix_note", "parse_check_response", "plan_resend",
]
