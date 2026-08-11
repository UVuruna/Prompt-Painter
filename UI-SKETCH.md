# UI SKETCH — Setup ekran (za odobrenje, pre implementacije)

**STATUS 2026-07-30: implementirano I VERIFIKOVANO na živom prozoru —
Etapa A (ExpandableSwitch + BG podmeni parametri), Etapa B (tri
grupe sa expanderima, gear uklonjen), Etapa C (levo podešavanja /
desno kolekcije+output+Select). Živi smoke je našao i popravio dva
defekta: (1) restore podešavanja je otvarao SVE upaljene podmenije na
startu — sad ide kroz `quiet_restore`, panel se otvara kompaktno;
(2) tri grupe rame-uz-rame su tražile 1322 px i izbacivale desnu
kolonu sa ekrana — grupe se sada uvek slažu vertikalno, a i dva
panela (oba sajta) idu jedan POD drugi, pa ceo setup traži ~1030 px
(default prozor je 1120). Ovaj fajl ostaje kao referenca dok vlasnik
ne pregleda live izgled.**

*(Radni dokument za dogovor — briše se / prelazi u REWORK.md kad
odobriš. Odgovori: "da", "da ali izmeni X", ili nacrtaj preko.)*

---

## EKRAN 2 — Website GEN setup (levo podešavanja / desno input)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ [🏠]  [🌐][AI][💠][🔍][🖼][✂][🔎][📐]                    [▦ grid] [☀/☾]     │ ← top strip (ikone bez teksta)
├──────────────────────────────────────────┬─────────────────────────────────┤
│  LEVO — PODEŠAVANJA                      │  DESNO — INPUT                  │
│                                          │                                 │
│  Sites:   [✓] ChatGPT   [✓] Gemini       │  ┌───────────────────────────┐  │
│  (oba = jedna podešavanja za oba)        │  │  COLLECTIONS (.md)        │  │
│                                          │  │                           │  │
│  ── Pipeline ──────────────────────      │  │  calendar_prompts.md      │  │
│  [ON] BG removal                         │  │  character_prompts.md     │  │
│  [ON] Crop                               │  │  ...                      │  │
│  [OFF] Force aspect ratio            ▸   │  │                           │  │
│  [ON] Upscale                        ▾   │  │  (drop .md fajlove ovde)  │  │
│     ┌─────────────────────────────┐      │  └───────────────────────────┘  │
│     │ min side  [800] px          │      │  [Add…] [Add folder…]           │
│     │ filter: aspect 0.9 – 1.1    │      │  [Remove] [Clear]               │
│     └─────────────────────────────┘      │                                 │
│                                          │  Output:                        │
│  ── Run behavior ──────────────────      │  [U:/…/Watch Academy/assets  ]     │
│  [ON] Report txt                         │  [Browse…]                      │
│  [ON] Safer retry                        │                                 │
│  [ON] Continue nudge                     │  [Select images…]               │
│  [OFF] AI checker                    ▸   │                                 │
│  [⏱] Pacing                          ▸   │                                 │
│                                          │                                 │
│  ── Prompt ────────────────────────      │                                 │
│  Background: [default ▾]  (custom→⬛)    │                                 │
│  Style:      [None ▾]                    │                                 │
│  New chat:   [collection ▾]              │                                 │
│  Helpers: [ON]no mirror [OFF]no empty    │                                 │
│           [ON]no grainy                  │                                 │
│                                          │                                 │
│  [▶ START]   [Pause]   [Stop]            │                                 │
├──────────────────────────────────────────┴─────────────────────────────────┤
│  DASHBOARD (uvek delimično vidljiv ispod — screen 3)                       │
└────────────────────────────────────────────────────────────────────────────┘
```

## Mehanika EXPAND/COLLAPSE po switchu (ono što si opisao)

```
Ugašen switch — podmeni ne postoji:
  [OFF] Upscale

Paljenje switcha AUTOMATSKI uradi prvi expand (▾), uvučeno dole-desno:
  [ON] Upscale                        ▾
     ┌─────────────────────────────┐
     │ min side  [800] px          │
     │ filter: [aspect 0.9 – 1.1]  │
     └─────────────────────────────┘

Klik na ▾/▸ ručno skuplja/širi; gašenje switcha skriva podmeni:
  [ON] Upscale                        ▸
```

Ko ima podmeni (▸), a ko je čist switch:

| Kontrola | Podmeni (expand ispod nje) |
|---|---|
| BG removal | mode: auto / white / black / CUSTOM boja (color wheel + tolerancija ± % po kanalu) • reach: samo od ivice (flood) / svuda — ISTO kao standalone BG tool (vlasnik 2026-07-29) |
| Crop | — |
| Force aspect ratio | W : H polja + vizuelni canvas |
| Upscale | min side + filter editor |
| AI checker | ✓ prompt match • Fixer AI (on/off + api/website) |
| Pacing (⏱ red, nije switch) | pause min–max • action delay • on degrade |
| Background = "custom" | color wheel + swatch odmah pored |
| Helpers, Report, Safer retry, Nudge | — (čisti switchevi) |

**Jedan globalni "Settings ⚙" gear NESTAJE** — sve fine-tune stavke
sele u podmenije svojih switcheva (gore navedeno).

---

## EKRAN 2b — alati (BG / Crop / Upscale / Aspect / AI check)

Ista podela; desna strana ima JEDNU ili DVE drop sekcije:

```
├──────────────────────────────────────┬─────────────────────────────────────┤
│  LEVO — PODEŠAVANJA alata            │  DESNO — INPUT                      │
│                                      │  ┌───────────────────────────────┐  │
│  [switchevi/opcije tog alata,        │  │  IMAGES (folder ili fajlovi)  │  │
│   isti expand princip]               │  │  (drop ovde)                  │  │
│                                      │  └───────────────────────────────┘  │
│  [▶ START]  [Pause]  [Stop]          │  ┌───────────────────────────────┐  │
│                                      │  │  PROMPT SHEETS (.md) — samo   │  │
│                                      │  │  AI check (opciono)           │  │
│                                      │  └───────────────────────────────┘  │
```

---

## Već potvrđeno rečima vlasnika (2026-07-29, implementira se odmah)

- **[▦ grid] dugme** vidljivo SAMO dok je dashboard na ekranu.
- **Dashboard se NE prikazuje stalno** — pojavljuje se tek kad se
  pokrene prvi posao; setup ekran pre starta nema dashboard ispod.

## Pitanja (odgovori uz "da/ne" za skicu)

1. Grupisanje levo — da li ovako: **Pipeline / Run behavior / Prompt**,
   ili drugačije grupe/redosled?
2. "Show:" red nestaje — **Sites checkboxi** na vrhu levog panela su
   jedini izbor sajtova. OK?
3. Queue lista (collections) seli DESNO kao drop-zona + lista. OK?
4. `Select images…` stoji desno ispod Output-a. OK?
