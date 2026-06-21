---
name: SetArc
description: Editorial-archive workbench for DJ sets — monospace, hairline grid, square geometry, near-monochrome with a dark default and a warm paper theme.
themes:
  dark:
    bg: "#0d0d0d"
    surface: "#161616"
    surface-2: "#1c1c1c"
    elevated: "#222222"
    border: "#2b2b2b"
    border-strong: "#3d3d3d"
    muted: "#787878"
    faint: "#555555"
    fg: "#c4c4c4"
    fg-strong: "#ededed"
    danger: "#d8593f"
  paper:
    bg: "#e9e5db"
    surface: "#f1eee6"
    surface-2: "#eae6dc"
    elevated: "#e2ddd0"
    border: "#cdc7b8"
    border-strong: "#b2ab99"
    muted: "#86806f"
    faint: "#a79f8d"
    fg: "#2a2823"
    fg-strong: "#15140f"
    danger: "#a83a22"
typography:
  ui-font: "var(--font-ibm-plex-mono), ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace"
  brand:
    fontWeight: 600
    textTransform: "uppercase"
    letterSpacing: "0.16em"
  title:
    fontWeight: 600
    textTransform: "uppercase"
    letterSpacing: "0.12em"
    fontSize: "0.875rem"
  body:
    fontWeight: 400
    fontSize: "0.875rem"
    lineHeight: 1.5
  label:
    fontWeight: 500
    textTransform: "uppercase"
    letterSpacing: "0.12em"
    fontSize: "0.625rem"
  data:
    fontWeight: 400
    fontFeature: "'tnum'"
rounded:
  all: "0px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  "2xl": "32px"
components:
  button-primary:
    backgroundColor: "{fg-strong}"
    textColor: "{bg}"
    rounded: "0px"
    textTransform: "uppercase"
    padding: "0 16px"
    height: "40px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{fg}"
    border: "1px solid {border-strong}"
    rounded: "0px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{muted}"
    rounded: "0px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{danger}"
    border: "1px solid {danger}"
    rounded: "0px"
  card:
    backgroundColor: "{surface}"
    border: "1px solid {border}"
    rounded: "0px"
    padding: "16px"
  input:
    backgroundColor: "{bg}"
    textColor: "{fg}"
    border: "1px solid {border}"
    rounded: "0px"
    height: "40px"
    padding: "0 12px"
  badge-neutral:
    backgroundColor: "{elevated}"
    textColor: "{muted}"
    rounded: "0px"
    textTransform: "uppercase"
    padding: "2px 8px"
  badge-danger:
    backgroundColor: "transparent"
    textColor: "{danger}"
    border: "1px solid {danger}"
    rounded: "0px"
---

# Design System: SetArc — Editorial Archive

## 1. Overview

**Creative North Star: "The Printed Archive."**

SetArc reads like a printed catalogue of a record library. The interface is monospace throughout, laid out on a hairline grid, with square geometry and almost no color — ink on a near-black field by default, or on warm paper when toggled. Density is editorial, not dashboard-like: dense columns of type, numbered lists, uppercase section labels, and tabular figures that align like a typeset index.

The system is built from **filets and type**, not fills and shadows. Depth comes from 1px hairline borders and a tight neutral stack, never from drop shadows or rounded cards. The only color in the entire system is a single restrained red, reserved for errors and destructive actions; everything else — including Camelot keys and mix-status, which carried color in the previous system — is rendered in monochrome, distinguished by weight, position, and uppercase labels.

This system explicitly rejects: consumer-music-app warmth (soft pastels, oversized rounded artwork); generic SaaS dashboards (gradients, hero-metric templates, identical card grids); legacy DJ software density and skeuomorphism; and AI-tool-hype glassmorphism. It is a quiet, typographic, archival instrument.

**Key Characteristics:**
- Monospace (IBM Plex Mono) for the entire interface — chrome, labels, body, and data
- Hairline grid: a three-zone editorial shell (INDEX / CONTENT / MARGINALIA) divided by 1px rules
- Square geometry everywhere (`radius: 0`), no shadows except a dimmed modal backdrop
- Near-monochrome: one red (`danger`) only, for errors and destructive actions
- Two themes — **dark** (default, near-black) and **paper** (warm cream) — toggled at runtime, persisted, no FOUC
- Tabular figures (`tnum`) on every metric so numbers align like a typeset index

## 2. Colors

Two monochromatic themes share the same token names, swapped at runtime via `html[data-theme="paper"]`. The dark theme is the default (`:root`).

### Dark (default)
A neutral near-black field with light-gray ink. `bg #0d0d0d`, `surface #161616`, `elevated #222222`, hairline `border #2b2b2b` / `border-strong #3d3d3d`, `muted #787878`, `faint #555555`, body `fg #c4c4c4`, emphasis `fg-strong #ededed`.

### Paper (toggle)
A warm cream field with near-black ink. `bg #e9e5db`, `surface #f1eee6`, `elevated #e2ddd0`, hairline `border #cdc7b8` / `border-strong #b2ab99`, `muted #86806f`, `faint #a79f8d`, body `fg #2a2823`, emphasis `fg-strong #15140f`.

### The one color
**Danger red** — `#d8593f` (dark) / `#a83a22` (paper). The *only* hue in the system. Used exclusively for error messages, destructive actions (delete), and invalid input (e.g. malformed Camelot notation). It never appears as decoration or as a status/quality indicator.

### Named Rules
**The Monochrome Rule.** Nothing carries hue except `danger`. Camelot keys, mix-status, transition quality, risk levels, and provider states are all rendered in neutrals — distinguished by weight, uppercase labels, and position, never by color.

**The One-Red Rule.** Red means error or destruction, full stop. A low score, a "risky" transition, or a warning state is *not* an error and must stay monochrome.

## 3. Typography

**UI font:** IBM Plex Mono (`var(--font-ibm-plex-mono)`, with `ui-monospace, SF Mono, Cascadia Code, Menlo` fallback), loaded via `next/font/google`. It is exposed through a single swappable token `--font-ui` (and aliased to `--font-sans`/`--font-mono`) so a licensed face such as Monument Grotesk Mono can be dropped in by replacing one `.woff2` and one variable.

**Character:** One monospace for everything — brand, headings, labels, body, and data. Personality comes from uppercase tracking on labels and the tabular-figure treatment on metrics, not from a second family.

### Hierarchy
- **Brand** (600, uppercase, `0.16em` tracking): the `SETARC` wordmark.
- **Title** (600, uppercase, `0.12em` tracking, `text-sm`): page titles (rendered by `PageLayout`) and card/section/modal headers.
- **Body** (400, `text-sm`, 1.5 line-height): descriptions and prose; cap at ~46–60ch.
- **Label** (500, uppercase, `0.12em` tracking, `~10px`): every column/section header and form-field label.
- **Data** (400, `font-variant-numeric: tabular-nums`): every BPM, Camelot key, energy, duration, and count, via the `.tnum` utility.

### Named Rules
**The Tabular Rule.** Every number a DJ scans is set in tabular figures (`.tnum`) so columns align like a typeset index.

**The Mono Rule.** One monospace family for the entire UI. No serif headlines, no second sans "for contrast" — hierarchy is weight, size, case, and tracking.

## 4. Elevation

Flat by definition. Depth is conveyed entirely by **hairline borders and the neutral stack** (`bg → surface → surface-2 → elevated`). There are **no shadows** anywhere — the modal separates from the page with a hairline border and a dimmed (not blurred) backdrop (`bg-black/70`).

### Named Rules
**The Hairline Rule.** Structure is drawn with 1px borders. If a region needs separating, add a filet or step the tonal stack — never a shadow, never a radius.

## 5. Components

### Buttons (`rounded: 0`, uppercase, tracked)
- **Primary:** solid `fg-strong` fill, `bg`-colored ink, hover softens to `fg`. The single loudest action on a screen.
- **Outline:** transparent, `border-strong` edge, foreground text; hover fills to `elevated`.
- **Ghost:** transparent, muted text; hover fills to `elevated`. For low-emphasis/icon actions.
- **Danger:** transparent with a `danger` border and text; hover inverts to a `danger` fill. Destructive actions only.
- **Focus:** 1px `fg` ring. Disabled drops to 50% opacity.

### Badges (`rounded: 0`, uppercase, tracked, `~10px`)
- **Neutral:** `elevated` background, `muted`/`fg` text. This is the default and near-universal badge — platform tags, statuses, transition classes, risk levels all use it.
- **Danger:** transparent with a `danger` border and text. The only colored badge.

### Cards / Containers
- **Background:** `surface` on the `bg` floor; **1px `border` hairline; `radius: 0`; no shadow.**
- **Padding:** 16px (`p-4`) default; header rows use 20px horizontal (`px-5`). Prefer hairline-divided sections over nested cards.

### Inputs / Fields (`rounded: 0`)
- **Style:** inset `bg` (darker than the surface) with a 1px `border`, 40px tall; placeholder `faint`.
- **Focus:** border shifts to `border-strong` with a 1px `fg` ring; no layout shift.
- **Error:** `danger` border + a `danger` hint line (e.g. invalid Camelot notation).
- **Field label:** uppercase, tracked, `~10px`, muted, above the control.

### Shell & Navigation — the editorial grammar
- **EditorialShell:** a three-zone, hairline-divided layout. **INDEX** (left, ~180px) holds the `SETARC` wordmark, tagline, uppercase nav (active = underlined), and a footer with a live `HH:MM:SS` clock and the theme toggle. **CONTENT** (center) carries the page's primary object. **MARGINALIA** (right, ~240px, optional per page) carries contextual stats, actions, and notes.
- **PageLayout:** renders the uppercase page title + optional meta over the content, plus the optional marginalia column with its hairline. Below the `lg` breakpoint, INDEX collapses to a top bar and marginalia drops below the content.

### Progress & Coverage Bars
- **Style:** 8px track on `elevated`, **square** (no radius), `fg` fill. Determinate bars animate width; indeterminate bars shimmer (`animate-shimmer`, 1.6s).

### Modal
- **Style:** `fixed inset-0`, `z-50`, dimmed `bg-black/70` backdrop (no blur); `surface` panel with a `border-strong` hairline, `radius: 0`, no shadow. Header with title + `×`, optional right-aligned footer actions.
- **Doctrine:** modals are the exception. Used for focused edits (manual track values, rename, delete confirmation).

### Empty States
- **Style:** dashed `border` container, centered icon (faint) + title (`fg-strong`) + one muted line + a single action. Teaches the next step in the flow.

## 6. Do's and Don'ts

### Do:
- **Do** keep the entire UI monospace; hierarchy is weight, case, and tracking.
- **Do** draw structure with 1px hairlines and the neutral stack — flat, square, no shadows.
- **Do** set every metric in tabular figures (`.tnum`).
- **Do** render Camelot keys, mix-status, and quality/risk in monochrome.
- **Do** keep both themes in sync — every surface must read correctly in dark *and* paper.
- **Do** use uppercase tracked labels for column/section headers and field labels.

### Don't:
- **Don't** introduce any color other than `danger`, and only for errors/destruction.
- **Don't** add rounded corners or shadows — `radius: 0`, hairlines only (The Hairline Rule).
- **Don't** color-code keys or mix quality (The Monochrome Rule).
- **Don't** introduce a second type family or a non-mono face in UI chrome (The Mono Rule).
- **Don't** treat a low score or "risky" transition as an error — keep it monochrome (The One-Red Rule).
- **Don't** put `faint` on anything that must be read at body size; use `muted` for readable secondary text.
