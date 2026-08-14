"""Same-named sheets in different folders run together (owner
2026-08-14, the two continents sheets): their report files are
disambiguated per queue by ``unique_report_stems`` — the old behavior
refused the whole run with a rename demand, the tool dictating the
consuming project's structure."""

from pathlib import Path

from painter.run_report import unique_report_stems


def test_lone_stems_stay_bare():
    """No collision — every existing report file keeps its name."""
    a = Path("U:/WA/prompts/continents/continents_prompts.md")
    b = Path("U:/WA/prompts/axes/axes_prompts.md")
    assert unique_report_stems([a, b]) == {
        str(a): "continents_prompts",
        str(b): "axes_prompts",
    }


def test_colliding_stems_absorb_the_parent_folder():
    """The Watch Academy pair: continents/ and weekday/ both hold a
    continents_prompts.md — each report gets its folder's name."""
    a = Path("U:/WA/prompts/continents/continents_prompts.md")
    b = Path("U:/WA/prompts/weekday/continents_prompts.md")
    c = Path("U:/WA/prompts/axes/axes_prompts.md")
    stems = unique_report_stems([a, b, c])
    assert stems[str(a)] == "continents__continents_prompts"
    assert stems[str(b)] == "weekday__continents_prompts"
    assert stems[str(c)] == "axes_prompts"
    assert len(set(stems.values())) == 3


def test_same_parent_name_climbs_higher():
    """Two sheets whose PARENT folders also share a name diverge one
    level further up."""
    a = Path("U:/WA/alpha/mood/sheet.md")
    b = Path("U:/WA/beta/mood/sheet.md")
    stems = unique_report_stems([a, b])
    assert stems[str(a)] == "alpha__mood__sheet"
    assert stems[str(b)] == "beta__mood__sheet"


def test_run_sheet_writes_the_disambiguated_report(tmp_path):
    """``run_sheet(report_stem=...)`` lands the report under the
    queue-unique name, not the bare stem."""
    from painter.config.paths import REPORT_SUFFIX, STATE_DIRNAME
    from painter.config.sites import SITES
    from painter.runner import run_sheet
    from tests.test_runner_images import FAST, FakeDriver, make_sheet

    sheet = make_sheet(tmp_path)
    driver = FakeDriver(SITES["chatgpt"])
    run_sheet(
        sheet, driver, tmp_path / "out", "chatgpt", FAST,
        log=lambda s: None,
        report_stem="weekday__" + sheet.source.stem,
    )
    state = tmp_path / "out" / STATE_DIRNAME / "chatgpt"
    assert (
        state / ("weekday__" + sheet.source.stem + REPORT_SUFFIX)
    ).exists()
    assert not (state / (sheet.source.stem + REPORT_SUFFIX)).exists()
