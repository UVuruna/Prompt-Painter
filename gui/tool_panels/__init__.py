"""``gui.tool_panels`` — the standalone in-place tools' persistent
settings panels, one cohesive module per family since the root Rule
#20 package split (2026-07-30):

* [Layout Constants](layout.md) — the leaf every panel family
  (including ``gui.agent_panel``/``gui.api_panel``) imports for the
  two-column-dense metrics, with no risk of a cycle.
* [Base Tool Settings Panel](base.md) — ``ToolSettingsPanel``: the
  input picker, the shared filter gate, the Advanced collapsible and
  the Start/Pause/Stop row.
* [BG Settings Panel](bg.md) — ``BgSettingsPanel``.
* [Geometry Settings Panels](geometry.md) — ``CropSettingsPanel``,
  ``UpscaleSettingsPanel``, ``AspectSettingsPanel``.
* [Image Checker Settings Panel](image_checker.md) —
  ``ImageCheckerSettingsPanel``.

A pure re-export shell, so every existing ``from .tool_panels import
BgSettingsPanel`` / ``DENSE_COL_WRAP_PX`` call site kept working
unchanged across the split.
"""

from .layout import (
    ASPECT_DIALOG_ENTRY_W,
    DENSE_COL_GAP_PX,
    DENSE_COL_WRAP_PX,
    SETTINGS_GLYPH_COLLAPSED,
    SETTINGS_GLYPH_EXPANDED,
)
from .base import ToolSettingsPanel
from .bg import BG_MODE_BY_LABEL, BG_REACH_BY_LABEL, BG_SWATCH_PX, BgSettingsPanel
from .geometry import (
    AspectSettingsPanel,
    CropSettingsPanel,
    UpscaleSettingsPanel,
)
from .image_checker import ImageCheckerSettingsPanel

__all__ = [
    "ASPECT_DIALOG_ENTRY_W", "DENSE_COL_GAP_PX", "DENSE_COL_WRAP_PX",
    "SETTINGS_GLYPH_COLLAPSED", "SETTINGS_GLYPH_EXPANDED",
    "ToolSettingsPanel", "BgSettingsPanel", "BG_MODE_BY_LABEL",
    "BG_REACH_BY_LABEL", "BG_SWATCH_PX", "CropSettingsPanel",
    "UpscaleSettingsPanel", "AspectSettingsPanel",
    "ImageCheckerSettingsPanel",
]
