"""PainterGui — composed from five responsibility mixins.

Godfile refactor step 7/8 (see gui/___gui.md): ``gui/__init__.py`` used to
hold one ~3350-line ``class PainterGui:`` (the god-class) plus ``main()``.
Both moved here. ``PainterGui`` itself is now just the MRO glue — every
method it exposes is defined on exactly one of the five mixins below (see
each mixin module's own docstring for what it owns); ``PainterGui``
contributes no code of its own beyond composing them. ``BuildMixin`` is
the ONLY mixin with an ``__init__`` — the other four run on the
attributes it sets, via ``self.``.
"""

from __future__ import annotations

import ttkbootstrap as tb

from .app_build import BuildMixin
from .app_jobs import SiteJobsMixin
from .app_settings import SettingsMixin
from .app_tools import ToolJobsMixin
from .app_views import ViewMixin


class PainterGui(
    BuildMixin, ViewMixin, SiteJobsMixin, ToolJobsMixin, SettingsMixin,
):
    """The whole PromptPainter window — see the five mixins above for
    what each part of the class actually does."""


def main() -> None:
    root = tb.Window(themename="darkly")
    PainterGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
