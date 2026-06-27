# Veles Design System

**Veles** — AI financial analyst for due diligence and market analysis.

A dark, premium chat interface. The product feels like a $10,000 tool: minimal,
restrained, mostly dark — with rainbow accents reserved for moments of intelligence
(input focus, the AI thinking). Reference aesthetic: refero.design.

## Sources
- `uploads/photo_2026-06-24_11-05-17.jpg` — screenshot of the composer / input island
  (glassmorphism floating bar with animated rainbow conic-gradient border).
- Brand brief supplied by the user (palette, blur values, type direction).

No codebase or Figma was provided; the system is built from the brief + screenshot.

---

## CONTENT FUNDAMENTALS
- **Language:** All product copy is **English**. Keep financial terms precise (due diligence, revenue, EBITDA).
- **Voice:** Calm, expert, concise. The analyst is a quiet authority — never chatty,
  never salesy. Short declarative sentences.
- **Person:** Address the user as "you" sparingly; the product mostly speaks *about the work* ("Analyzing filings…") rather than about itself.
- **Casing:** Sentence case everywhere. No ALL-CAPS except tiny labels (tracking-wide).
- **Placeholders:** Inviting, low-pressure — e.g. "Ask follow up…".
- **Emoji:** None. The brand is austere; intelligence is shown through motion + light,
  not emoji or exclamation.
- **Numbers/data:** Treated as first-class — monospace (Geist Mono), right-aligned in
  tables, never decorative. Avoid stat-slop.

## VISUAL FOUNDATIONS
- **Background:** Animated dark **mesh/aurora gradient** — deep navy `#0a0a0f`, dark
  purple `#12082a`, dark teal `#071a2e` — slowly drifting like aurora borealis
  (60–80s loops, ultra-slow). Never static, never bright.
- **Surfaces:** Glassmorphism. Cards & bubbles: `rgba(255,255,255,0.05)` +
  `backdrop-filter: blur(16px)` + `1px` border `rgba(255,255,255,0.1)`. The input
  island is stronger: `rgba(20,20,30,0.7)` + `blur(20px)`.
- **Rainbow accent:** A rotating **conic-gradient** (`--rainbow`). Appears ONLY on key
  moments: input focus and the AI thinking state. Otherwise the UI is dark and quiet.
  Driving property: `--rainbow-angle` animated 0→360°.
- **Type:** Geist (geometric sans) + Geist Mono for numbers/code. White primary text,
  `rgba(255,255,255,0.4)` secondary. Tight tracking on headings.
- **Radii:** Generous & soft — cards `16–24px`, the island `24–32px`, pills `999px`.
- **Shadows:** Deep, soft, diffuse — no hard edges. `0 16px 60px rgba(0,0,0,.55)` on
  the island; subtle purple glow (`--shadow-glow`) on active intelligence states.
- **Motion:** Slow and silky. `cubic-bezier(0.22,1,0.36,1)`, 160–600ms. Fades and
  gentle rises; never bouncy. The only continuous motion is the aurora + rainbow ring.
- **Hover:** Lighten surface (`rgba(255,255,255,0.08)`) + border to 0.18. No color
  shifts.
- **Press:** Slight scale-down (0.98) + dim. Quick.
- **Borders:** Always thin (1px) and translucent white. No solid colored borders
  except the animated rainbow ring.
- **Transparency/blur:** Core to the identity — every surface floats over the aurora.
- **Imagery vibe:** Cool, dark, deep-space. Minimal photography; light is the hero.

## ICONOGRAPHY
- **Lucide** (https://lucide.dev) — thin, geometric stroke icons (1.5px) match Geist's
  geometry. Loaded from CDN (`lucide@latest`). Substitution flagged: no custom icon set
  was provided, so Lucide is the chosen stand-in (closest stroke style to the brand).
- **No emoji.** No unicode-glyph icons. Stroke icons only, `rgba(255,255,255,0.7)`,
  inheriting `currentColor`.
- A simple **rainbow-ring mark** stands in for the Veles logo until a real asset is
  supplied.

---

## INDEX
- `styles.css` — entry point (`@import`s all tokens + fonts).
- `tokens/` — `colors.css`, `typography.css`, `spacing.css`, `fonts.css`.
- `components/core/` — Button, IconButton, Input, Card, Badge, Avatar, Switch, Tabs.
- `ui_kits/veles-chat/` — the Veles analyst chat interface (full screen recreation).
- `guidelines/` — foundation specimen cards (Type / Colors / Spacing / Brand).
- `SKILL.md` — Agent Skill manifest.

## CAVEATS / OPEN QUESTIONS
- **Fonts:** Geist is loaded from Google Fonts. If you have licensed Söhne or self-hosted
  Geist files, send them and I'll swap in `@font-face`.
- **Logo:** No real Veles logo was provided — using a placeholder rainbow-ring mark.
- **Icons:** Lucide is a substitution; confirm or provide the real icon set.
