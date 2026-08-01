# BG Settings Panel — Flow

**About:** [description](../__about/bg.md)

## Layout

Fills the [Base Tool Settings Panel](../__flow/base.md) `_build_extra`
(right-column, above Advanced) and `_build_advanced` zones:

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph EXTRA["_build_extra — always visible"]
        M["Background mode dropdown<br/>Auto / Black / White / Custom color"]
        C["Custom-color block (Custom mode only)<br/>hex entry + swatch-button + ± tolerance spinner<br/>+ live '± N levels · #hex…#hex' hint"]
        R["Remove matching pixels dropdown<br/>Touching the edge / Everywhere + hint"]
        M -- "mode == Custom" --> C
        M --> R
    end
    subgraph ADV["Advanced — safety guards, in percent"]
        B["black bg guard %"]
        W["white bg guard %"]
        CO["custom bg guard %"]
    end
    EXTRA --> ADV
```

Pixel-picking a swatch color opens `ColorChooserDialog` as a modal
over this panel, not a zone of it.
