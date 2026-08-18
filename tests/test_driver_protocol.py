"""``painter.driver.protocol`` — one prompt into the composer, provably
sent.

``submit_with_image`` raises ``AttachNotConfigured`` LOUDLY and
IMMEDIATELY (before touching the page at all) when a site's
``attach_menu_path`` is empty; with the real captured selectors it runs
the human path — expand the "+" menu, pick the add-image option, attach
the file (``set_input_files`` for ChatGPT's hidden input, the
file-chooser interception for Gemini's OS dialog), WAIT for the composer
preview, then paste + send — and never sends when the preview never
appears. ``submit_prompt``'s text-only flow is byte-identical after being
routed through the shared ``_paste_and_send``. F1: a submit is not "sent"
until CONFIRMED (composer emptied + our text is the newest user turn).

Split from ``tests/test_driver.py`` alongside the driver package (audit
``docs/AUDIT-OOP-2026-08-18.md`` -> R4). Shared fakes:
``tests/driver_fakes.py``.
"""

import time
from dataclasses import replace
import pytest
from painter.config import SITES, Timing
from painter.driver import (
    AttachNotConfigured,
    DriverError,
    SelectorRot,
    SiteDriver,
    normalize_text,
)
from driver_fakes import (
    FAST,
    FakeLocator,
    FakePage,
    PresentLocator,
    _driver,
)


def _wire_send_flow(site, page, prompt_box, send):
    """Wire the F1 confirmed-send flow onto ``prompt_box``/``send``:
    ``page.composer`` becomes ``prompt_box`` (so the keyboard fakes
    mutate the SAME locator ``_composer_text()`` reads back), and
    ``send``'s click copies the composer's CURRENT text into a
    user-turn FakeLocator registered at ``site.user_turn[0]`` before
    emptying the composer — mirroring a real send: the box clears and
    the text becomes the newest user turn, which is exactly what
    ``_confirm_sent`` polls for. Used by every test that drives
    ``submit_prompt``/``submit_with_image`` all the way through
    confirmation (including the reload-recovery tests, where the hook
    must be re-wired onto the send button injected post-reload)."""
    page.composer = prompt_box

    def _on_send_click():
        page.locators[site.user_turn[0]] = FakeLocator(
            "user_turn", page, text=prompt_box.text
        )
        prompt_box.text = ""

    send.on_click = _on_send_click
    return send


@pytest.mark.parametrize("site_key", ["chatgpt", "gemini"])
def test_shipped_sites_have_image_attach_configured(site_key):
    """The owner captured the '+' menu selectors (UV/Add Photo), so
    image attach is ENABLED for both sites: a "+" step, an add-image
    option step, and a preview to wait for."""
    site = SITES[site_key]
    assert len(site.attach_menu_path) >= 2
    assert all(step for step in site.attach_menu_path)  # no empty step
    assert site.attach_preview != ()


def test_chatgpt_uses_a_hidden_input_gemini_uses_the_file_chooser():
    """ChatGPT exposes #upload-photos (set_input_files, no OS dialog);
    Gemini opens an OS dialog with no exposed input (file-chooser)."""
    assert SITES["chatgpt"].file_input != ()
    assert SITES["gemini"].file_input == ()


def test_submit_with_image_raises_loudly_when_not_configured():
    site = replace(SITES["chatgpt"], attach_menu_path=())
    page = FakePage()
    driver = _driver(site, page)

    with pytest.raises(AttachNotConfigured):
        driver.submit_with_image("C:/out/img.png", "put the hero in")

    # loud and immediate: no click/attach action was ever taken —
    # _ensure_ready/capture_baseline only READ selectors (safely, on an
    # empty page) before the gate raises
    assert page.calls == []


def _wire_attach(site, page, *, with_input: bool):
    """Wire the '+' step, the add-image option, the preview, prompt box
    and send onto ``page`` (and the hidden file input when the site uses
    one) — and the F1 confirmed-send flow, so every attach test can
    drive ``submit_with_image`` to completion. Returns the FakeLocator
    map for extra assertions."""
    plus = FakeLocator("plus", page)
    option = FakeLocator("option", page)
    preview = FakeLocator("preview", page)
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.attach_menu_path[0][0]: plus,
        site.attach_menu_path[1][0]: option,
        site.attach_preview[0]: preview,
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    loc = {
        "plus": plus,
        "option": option,
        "preview": preview,
        "prompt_box": prompt_box,
        "send": send,
    }
    if with_input:
        # a real <input type=file> is routinely hidden by design — prove
        # the driver still finds it (require_visible=False)
        file_input = FakeLocator("file_input", page, visible=False)
        page.locators[site.file_input[0]] = file_input
        loc["file_input"] = file_input
    return loc


def test_submit_with_image_sequence_chatgpt_hidden_input():
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in the scene")

    assert loc["file_input"].set_files == "C:/out/hero.png"
    calls = page.calls
    i_plus = calls.index(("click", "plus"))
    i_files = calls.index(
        ("set_input_files", "file_input", "C:/out/hero.png")
    )
    i_text = calls.index(("insert_text", "put the hero in the scene"))
    i_send = calls.index(("click", "send"))
    # a person's path: expand "+", attach, THEN paste+send. The
    # add-image ROW is never clicked when the input is already there —
    # that click opens the native OS dialog (owner 2026-08-04)
    assert ("click", "option") not in calls
    assert i_plus < i_files < i_text < i_send


def test_submit_with_image_sequence_gemini_file_chooser():
    site = SITES["gemini"]
    page = FakePage()
    _wire_attach(site, page, with_input=False)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    # no exposed input -> the file went through the file-chooser
    assert page.chooser_files == "C:/out/hero.png"
    calls = page.calls
    i_plus = calls.index(("click", "plus"))
    i_option = calls.index(("click", "option"))
    i_files = calls.index(("file_chooser_set_files", "C:/out/hero.png"))
    i_text = calls.index(("insert_text", "put the hero in"))
    i_send = calls.index(("click", "send"))
    assert i_plus < i_option < i_files < i_text < i_send


def test_submit_with_image_lazy_input_falls_back_to_the_chooser():
    """A menu that renders its <input type=file> only on the row click
    still attaches: the driver clicks the row inside file-chooser
    interception, so a native dialog is CONSUMED, never left open."""
    site = SITES["chatgpt"]
    page = FakePage()
    _wire_attach(site, page, with_input=False)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    assert page.chooser_files == "C:/out/hero.png"
    assert ("click", "option") in page.calls


def test_submit_with_image_list_passes_all_paths_in_order():
    """MULTI-ATTACH (faza 2): a list of resolved paths rides ONE picker
    interaction, order preserved — the prompt's "FIRST/SECOND attached
    image" depends on it."""
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image(
        ["C:/refs/Vader.png", "C:/refs/Luke.png"], "two refs"
    )

    assert loc["file_input"].set_files == [
        "C:/refs/Vader.png", "C:/refs/Luke.png",
    ]


def test_submit_with_image_single_item_list_unwraps_to_the_proven_form():
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image(["C:/out/hero.png"], "one ref")

    assert loc["file_input"].set_files == "C:/out/hero.png"


def test_submit_with_image_attaches_before_typing():
    """The image must be attached before the prompt is typed — the
    person expands the menu and attaches first, never types early."""
    site = SITES["chatgpt"]
    page = FakePage()
    _wire_attach(site, page, with_input=True)
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in")

    before_upload = []
    for call in page.calls:
        if call[0] in ("set_input_files", "file_chooser_set_files"):
            break
        before_upload.append(call)
    # only the "+" expand happens before upload — no prompt-box
    # interaction starts early
    assert before_upload == [("click", "plus")]


def test_submit_with_image_waits_for_the_preview_before_sending():
    """When the upload preview never appears, the driver must NOT send —
    it waits it out and fails loudly (the prompt never races the image)."""
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    del page.locators[site.attach_preview[0]]  # preview never shows up
    # shrink the preview wait so the loud failure is instant
    fast_preview = replace(FAST, image_ready_timeout_s=0.05)
    driver = SiteDriver(site, fast_preview, "http://unused")
    driver.page = page

    with pytest.raises(SelectorRot):
        driver.submit_with_image("C:/out/hero.png", "put the hero in")

    # the file WAS attached, but no prompt/send ever happened
    assert loc["file_input"].set_files == "C:/out/hero.png"
    assert not any(c[0] == "insert_text" for c in page.calls)
    assert ("click", "send") not in page.calls


def test_submit_prompt_empty_composer_skips_delete():
    """Owner 2026-07-29: "ako je empty ne treba delete" — an EMPTY
    composer gets NO Ctrl+A/Delete, just click, insert_text, send. The
    send is CONFIRMED via the wired flow (composer clears, our text
    becomes the newest user turn)."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    assert page.calls == [
        ("click", "prompt_box"),
        ("insert_text", "hello world"),
        ("click", "send"),
    ]


def test_submit_prompt_composer_with_leftover_text_deletes_first():
    """The companion case: the composer STARTS with leftover text — the
    driver clears it (Ctrl+A + Delete) before pasting the new prompt."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page, text="old junk")
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    assert page.calls == [
        ("click", "prompt_box"),
        ("press", "Control+A"),
        ("press", "Delete"),
        ("insert_text", "hello world"),
        ("click", "send"),
    ]


def test_submit_prompt_still_uses_only_prompt_box_and_send_selectors():
    """submit_prompt must not accidentally start requiring the image
    attach selectors — it stays text-only."""
    site = SITES["gemini"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello gemini")  # must not raise / must not hang

    assert ("insert_text", "hello gemini") in page.calls
    # no attach-menu / file interaction happened on a plain text submit
    assert not any(
        c[0] in ("set_input_files", "file_chooser_set_files")
        for c in page.calls
    )


def test_submit_prompt_recovers_via_reload_when_send_button_missing():
    site = SITES["gemini"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    # the send button is ABSENT until the fake reload "fixes" the DOM —
    # mirrors the real site coming back sane after a refresh
    page.locators = {site.prompt_box[0]: prompt_box}
    page.composer = prompt_box
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        prompt_box.text = ""  # a reload wipes the unsent composer text
        page.locators[site.send_button[0]] = send
        _wire_send_flow(site, page, prompt_box, send)

    page.reload = reload_and_recover
    driver = _driver(site, page)
    logs: list[str] = []

    driver.submit_prompt("hello gemini", logs.append)

    assert page.calls.count(("reload",)) == 1  # exactly one recovery attempt
    assert ("click", "send") in page.calls
    # the prompt was lost by the reload and re-pasted: typed twice
    # (the failed first attempt, then the post-reload retry)
    assert page.calls.count(("insert_text", "hello gemini")) == 2
    assert any("reloading the page" in line for line in logs)


def test_submit_with_image_reattaches_on_send_reload_recovery():
    """Review finding (owner 2026-07-23): a send-button reload recovery
    mid-``submit_with_image`` drops the attached image. The recovery must
    RE-ATTACH (re-walk the menu, re-set the file) before re-typing —
    otherwise it would silently send a TEXT-ONLY prompt under the
    reference-image filename (a Rule #1 violation)."""
    site = SITES["chatgpt"]
    page = FakePage()
    loc = _wire_attach(site, page, with_input=True)
    prompt_box = loc["prompt_box"]
    send = FakeLocator("send", page)
    # send button ABSENT until the fake reload "fixes" the DOM
    del page.locators[site.send_button[0]]
    base_reload = page.reload

    def reload_and_recover():
        base_reload()
        prompt_box.text = ""  # a reload wipes the unsent composer text
        page.locators[site.send_button[0]] = send
        _wire_send_flow(site, page, prompt_box, send)

    page.reload = reload_and_recover
    driver = _driver(site, page)

    driver.submit_with_image("C:/out/hero.png", "put the hero in", lambda s: None)

    assert page.calls.count(("reload",)) == 1
    # the image was attached TWICE — initial + re-attach after the reload
    assert page.calls.count(
        ("set_input_files", "file_input", "C:/out/hero.png")
    ) == 2
    # and the prompt DID go out with the image (send clicked), never
    # text-only-without-image
    assert ("click", "send") in page.calls
    assert ("insert_text", "put the hero in") in page.calls
    # the prompt was re-typed after the reload (the failed first attempt,
    # then the post-reload retry)
    assert page.calls.count(("insert_text", "put the hero in")) == 2


def test_submit_prompt_reload_recovery_gives_up_when_still_missing():
    """The send button is STILL missing after the reload -> the
    original SelectorRot propagates (stops the site), exactly as
    before this recovery existed — and only ONE reload is attempted,
    never a retry loop."""
    site = SITES["gemini"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    page.locators = {site.prompt_box[0]: prompt_box}
    page.composer = prompt_box  # so the typed text actually verifies
    driver = _driver(site, page)

    with pytest.raises(SelectorRot):
        driver.submit_prompt("hello gemini")

    assert page.calls.count(("reload",)) == 1


def test_submit_prompt_normal_path_never_reloads():
    """MUST NOT REGRESS: when the send button is present on the first
    try (the common case), no reload ever happens — proven both by the
    exact-call-list assertion above (test_submit_prompt_empty_composer_
    skips_delete) and explicitly here."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("hello world")

    assert ("reload",) not in page.calls


def test_timing_has_the_f1_protocol_fields():
    t = Timing()
    assert t.busy_clear_grace_s > 0
    assert t.send_confirm_timeout_s > 0


def test_sites_declare_a_user_turn_selector():
    assert SITES["chatgpt"].user_turn != ()
    assert SITES["gemini"].user_turn != ()


def test_ensure_ready_refreshes_over_a_stuck_busy_signal():
    """F1 root cause 1 (owner 2026-07-29): a busy signal STILL PRESENT
    from the previous item must never be sent over. LIVE-RUN HOTFIX:
    the driver now WAITS OUT a busy window first (a busy site may
    honestly be finishing the previous item — refreshing early KILLED
    it mid-work); only a busy signal that outlives ``busy_stuck_timeout_s``
    is stuck, and only then does the pre-send REFRESH happen — still
    strictly BEFORE the send click."""
    site = SITES["gemini"]
    timing = replace(FAST, busy_stuck_timeout_s=0.05)
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    logs: list[str] = []

    driver.submit_prompt("hello gemini", logs.append)

    i_reload = page.calls.index(("reload",))
    i_send = page.calls.index(("click", "send"))
    assert i_reload < i_send
    assert any("stuck" in line.lower() for line in logs)


def test_ensure_ready_busy_wait_uses_its_own_budget_not_generation():
    """The pre-send busy wait must be bounded by ``busy_stuck_timeout_s``
    — never by the (far longer) ``generation_timeout_s`` it used to
    borrow."""
    site = SITES["gemini"]
    timing = replace(
        FAST, busy_stuck_timeout_s=0.05, generation_timeout_s=600.0
    )
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page

    started = time.monotonic()
    driver.submit_prompt("hello gemini", lambda s: None)

    # bounded by busy_stuck_timeout_s (0.05s), not generation (600s)
    assert time.monotonic() - started < 30.0
    assert ("reload",) in page.calls


def test_ensure_ready_refreshes_at_once_when_busy_is_known_stuck():
    """When ``await_done`` returned on OUR loaded image while the busy
    signal was STILL set, the stop button is PROVABLY stuck — the next
    submit must refresh IMMEDIATELY instead of waiting the signal out
    (the 7 lost minutes)."""
    site = SITES["gemini"]
    timing = replace(FAST, busy_stuck_timeout_s=600.0)
    page = FakePage()
    page.locators[site.busy_signal[0]] = PresentLocator()  # never clears
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.locators[site.send_button[0]] = send
    _wire_send_flow(site, page, prompt_box, send)
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page
    driver._busy_known_stuck = True  # what await_done recorded
    logs: list[str] = []

    started = time.monotonic()
    driver.submit_prompt("hello gemini", logs.append)

    # no wait at all, despite a 600s busy budget
    assert time.monotonic() - started < 30.0
    assert ("reload",) in page.calls
    assert any("stuck" in line.lower() for line in logs)
    # the flag is consumed, never left latched for the next item
    assert driver._busy_known_stuck is False


def test_type_into_box_retypes_once_on_composer_mismatch():
    """A pasted prompt that lands GARBLED (the composer holds something
    else) gets ONE silent retype — the second attempt succeeds and the
    driver proceeds without raising."""
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    page.locators[site.prompt_box[0]] = prompt_box
    page.composer = prompt_box
    calls = {"n": 0}
    real_insert = page.keyboard.insert_text

    def flaky_insert_text(text):
        calls["n"] += 1
        if calls["n"] == 1:
            page.calls.append(("insert_text", text))
            prompt_box.text = "garbled nonsense"  # landed wrong
        else:
            real_insert(text)

    page.keyboard.insert_text = flaky_insert_text
    driver = _driver(site, page)

    driver._type_into_box("hello world")  # must not raise

    assert calls["n"] == 2
    assert prompt_box.text == "hello world"


def test_confirm_sent_raises_loudly_when_composer_never_empties():
    """No hook wired on ``send`` — the composer never clears and no user
    turn ever appears, so the send can never be CONFIRMED: a loud
    DriverError, never a silent proceed."""
    site = SITES["gemini"]
    timing = replace(FAST, send_confirm_timeout_s=0.05)
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)  # on_click does nothing
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    page.composer = prompt_box
    driver = SiteDriver(site, timing, "http://unused")
    driver.page = page

    with pytest.raises(DriverError) as exc:
        driver.submit_prompt("hello gemini")
    assert "NOT confirmed" in str(exc.value)


def test_submit_prompt_records_the_sent_head_for_anchoring():
    site = SITES["chatgpt"]
    page = FakePage()
    prompt_box = FakeLocator("prompt_box", page)
    send = FakeLocator("send", page)
    page.locators = {
        site.prompt_box[0]: prompt_box,
        site.send_button[0]: send,
    }
    _wire_send_flow(site, page, prompt_box, send)
    driver = _driver(site, page)

    driver.submit_prompt("Hello   WORLD, anchored")

    assert driver._sent_head == normalize_text(
        "Hello   WORLD, anchored"
    )[:60]
    # 2026-08-14: the FULL normalized prompt is recorded beside the
    # head — the anchor verdict is text-first now
    assert driver._sent_norm == normalize_text("Hello   WORLD, anchored")
