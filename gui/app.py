"""PainterGui — composed from six responsibility mixins.

Godfile refactor step 8/8 (see gui/___gui.md): ``gui/__init__.py`` used to
hold one ~3350-line ``class PainterGui:`` (the god-class) plus ``main()``.
Both moved here. ``PainterGui`` itself is now just the MRO glue — every
method it exposes is defined on exactly one of the six mixins below (see
each mixin module's own docstring for what it owns); ``PainterGui``
contributes no code of its own beyond composing them. ``BuildMixin`` is
the ONLY mixin with an ``__init__`` — the other five run on the
attributes it sets, via ``self.``. ``CheckerFixerMixin`` split out of
``SiteJobsMixin`` (step 8/8, once that module grew past the ~1000-line
Rule #20 budget) — the two still call into each other freely through the
shared MRO, exactly as when they were one class.
"""

from __future__ import annotations

import ttkbootstrap as tb

from .app_build import BuildMixin
from .app_checker_fixer import CheckerFixerMixin
from .app_jobs import SiteJobsMixin
from .app_settings import SettingsMixin
from .app_tools import ToolJobsMixin
from .app_views import ViewMixin


class PainterGui(
    BuildMixin, ViewMixin, SiteJobsMixin, CheckerFixerMixin, ToolJobsMixin,
    SettingsMixin,
):
    """The whole PromptPainter window — see the six mixins above for
    what each part of the class actually does."""


def main() -> None:
    root = tb.Window(themename="darkly")
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
