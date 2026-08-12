---
name: Cratory
description: Editorial-archive workbench for DJ sets — monospace, hairline grid, square geometry, near-monochrome with a dark default and a warm paper theme.
themes:
  dark:
    bg: "#0d0d0d"
    surface: "#161616"
    surface-2: "#1c1c1c"
    elevated: "#222222"
    border: "#2b2b2b"
    border-strong: "#3d3d3d"
    muted: "#898989"
    faint: "#555555"
    fg: "#c4c4c4"
    fg-strong: "#ededed"
    danger: "#d8593f"
  paper:
    bg: "#e9e5db"
    surface: "#f1eee6"
    surface-2: "#eae6dc"
    elevated: "#e2ddd0"
    border: "#a99e86"
    border-strong: "#7d735c"
    muted: "#676152"
    faint: "#847d68"
    fg: "#2a2823"
    fg-strong: "#15140f"
    danger: "#a83a22"
typography:
  ui-font: "var(--font-ibm-plex-mono), ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace"
  brand:
    fontWeight: 600
    textTransform: "uppercase"
    letterSpacing: "0.16em"
  title-page:
    fontWeight: 600
    textTransform: "uppercase"
    letterSpacing: "0.12em"
    fontSize: "0.875rem"
  title-section:
    fontWeight: 600
    textTransform: "uppercase"
    letterSpacing: "0.05em"
    fontSize: "1rem"
  body:
    fontWeight: 400
    fontSize: "0.875rem"
    lineHeight: 1.5
  label:
    fontWeight: 500
    textTransform: "uppercase"
    letterSpacing: "0.05em"
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
    padding: "set by the consumer, not by the component (16px recommended, 12px for dense cards)"
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
  badge-semantic:
    backgroundColor: "{elevated}"
    textColor: "{fg} | {muted}"
    rounded: "0px"
    textTransform: "uppercase"
    padding: "2px 8px"
    note: "primary/info/success collapse to the neutral rendering (Monochrome Rule); warning has its own monochrome treatment (badge-warning)"
  badge-warning:
    backgroundColor: "transparent"
    textColor: "{fg}"
    border: "1px dashed {border-strong}"
    rounded: "0px"
    textTransform: "uppercase"
    padding: "2px 8px"
    note: "attention without hue: the dashed 'provisional' grammar of empty states. Urgency scale: neutral fill < dashed ink < danger red"
  badge-danger:
    backgroundColor: "transparent"
    textColor: "{danger}"
    border: "1px solid {danger}"
    rounded: "0px"
---

# Product & Design: Cratory

## Product context

### Users

A single DJ — a personal user, self-hosted tool, no multi-tenancy. Usage context:
pre-session preparation. The user has a library of audio files on disk (`LIBRARY_ROOT`, the
source of truth for ownership) and uses streaming playlists and pasted tracklists (Spotify
or manual text/CSV import) as leads. They want to index the owned collection, import
BPM/key from Rekordbox, build a set, discover missing tracks and identify them in external
mixes, and acquire their files. Text metadata enrichment (title/artist/album/label/genre)
and on-disk tagging are the Organize section's job, not Cratory's.

The job to be done: go from "I have these streaming leads and these files on disk" to "I
have a ready set with reasoned transitions, the gaps filled, and the files of owned tracks
on disk".

### Purpose

Cratory is a personal workbench for DJ set preparation. It is not a player, not a social
app. It is the space where the library takes shape: import, normalization, on-disk library
indexing, BPM/key import from Rekordbox, file acquisition (Soulseek/slskd) with an archive
and download review, set building, gap analysis, discovery, exploring the collection by
record label (deterministic per-label aggregates, with the label read from the file tag),
and mix tracklist identification.

The flow (orientation strip on the dashboard, five stages): **Discover** (playlists/leads) →
**Acquire** (Soulseek/slskd) → **Organize** (text enrichment, tagging, organization: the
`/organize` section) → **Analyze⤴** (analysis in Rekordbox, BPM/key import) → **Play** (Set
Builder). Only Analyze still carries the ⤴: it leaves the app toward Rekordbox and returns
with an import. Organize used to carry it too, when it was a separate app. Library indexing (scan `LIBRARY_ROOT`, the disk is the library) is not a strip
stage: launch it from the "Index" button in the left nav (or it starts automatically at
startup).

Success = the user enters with raw playlists and leaves with a structured, annotated set, a
list of tracks to add, and their files acquired into the library.

### Brand personality

Sober, typographic, archival.

Cratory reads like a printed catalogue of a record collection: monospace everywhere, a
hairline grid, square geometry, almost no color. Crate digging remains a creative act —
there is energy in the process — but the energy is rendered with density, weight, and
typographic hierarchy, not with color. The tool neither disappears behind the data nor
overwhelms it with aesthetics: it composes it like a typographic index.

Tone: confident without being arrogant. Precise without being cold. It does not apologize
for being opinionated. Quiet, not shy.

### Anti-references

- **Consumer music app** (Spotify, Apple Music): too soft, rounded, designed for passive
  listening. Cratory is a work tool, not a jukebox.
- **Generic SaaS dashboard**: identical cards, purple or teal gradients, hero-metric
  templates, everything-centered layouts. AI scaffolding recognizable from a mile away.
- **Legacy DJ software** (Traktor, Rekordbox): overloaded with information, dense grids,
  2000s UX. Heavy, not fluidly navigable.
- **AI tool hype** ("2024 AI startup" style): pastel gradients, huge rounded cards,
  glassmorphism. **Not** to be confused with Cratory's **paper** theme, which is deliberate
  cream — warm paper with near-black ink, 1px hairlines and square geometry, not pastels or
  gradients.

### Design principles

The complete visual system (tokens, dark/paper themes, components) lives in the design
system below.

1. **Data first, narrative second.** The numbers (BPM, Camelot, energy) are the language.
   Show them with precision and calibrated density. The creative layer (AI, set narrative)
   wraps the data without replacing it.

2. **Every screen pushes forward.** The user has a goal — building a set. The nav groups
   the stations into three macro-phases, Discover (Playlists, Discovery, Shazam, Labels) →
   Collect (Library, Downloads) → Play (Set Builder, Sets), not independent sections. The
   path is always visible: the dashboard opens with a five-stage pipeline strip — Discover →
   Acquire → Organize⤴ → Analyze⤴ → Play — that tells you where you are in the cycle and
   what the next step is (library indexing is a button in the nav, not a strip stage).

3. **Dense but breathable.** A DJ library is dense data. The interface handles it without
   collapsing into a spreadsheet. Deliberate spacing, clear visual hierarchy, semantic
   grouping.

4. **Opinionated, not decorative.** Every visual choice must feel made for this tool — not
   borrowed from a generic design system. The language is monochrome: a single red for
   errors and destructive actions, hierarchy from weight, uppercase, tracking, and tabular
   figures (`tnum`), not from color.

5. **Experimental energy.** Discovery should feel like digging through crates of records.
   The set builder like composition, not filling out a form. The texture of the interface
   reflects the creative act it supports.

### Accessibility & inclusion

WCAG AA on text contrast (ratio ≥ 4.5:1 for body text, ≥ 3:1 for large text). No specific
requirement beyond contrast — personal tool, single user. Animations manageable via
`prefers-reduced-motion` where implemented.

---

# Design System: Cratory — Editorial Archive

## 1. Overview

**Creative North Star: "The Printed Archive."**

Cratory reads like a printed catalogue of a record library. The interface is monospace throughout, laid out on a hairline grid, with square geometry and almost no color — ink on a near-black field by default, or on warm paper when toggled. Density is editorial, not dashboard-like: dense columns of type, numbered lists, uppercase section labels, and tabular figures that align like a typeset index.

The system is built from **filets and type**, not fills and shadows. Depth comes from 1px hairline borders and a tight neutral stack, never from drop shadows or rounded cards. The only color in the entire system is a single restrained red, reserved for errors and destructive actions — with one narrow, documented brand exception, the Spotify glyph rendered in Spotify green (see The Brand-Green Exception). Everything else — including Camelot keys and mix-status, which carried color in the previous system — is rendered in monochrome, distinguished by weight, position, and uppercase labels.

This system explicitly rejects: consumer-music-app warmth (soft pastels, oversized rounded artwork); generic SaaS dashboards (gradients, hero-metric templates, identical card grids); legacy DJ software density and skeuomorphism; and AI-tool-hype glassmorphism. It is a quiet, typographic, archival instrument.

**Key Characteristics:**
- Monospace (IBM Plex Mono) for the entire interface — chrome, labels, body, and data
- Hairline grid: a three-zone editorial shell (INDEX / CONTENT / MARGINALIA) divided by 1px rules
- Square geometry everywhere (`radius: 0`), no shadows except a dimmed modal backdrop — the one allowed exception: the circular "hot" status dot (1.5px) in the dashboard pipeline strip
- Near-monochrome: one red (`danger`) only, for errors and destructive actions
- Two themes — **dark** (default, near-black) and **paper** (warm cream) — toggled at runtime, persisted, no FOUC
- Tabular figures (`tnum`) on every metric so numbers align like a typeset index

## 2. Colors

Two monochromatic themes share the same token names, swapped at runtime via `html[data-theme="paper"]`. The dark theme is the default (`:root`).

### Dark (default)
A neutral near-black field with light-gray ink. `bg #0d0d0d`, `surface #161616`, `elevated #222222`, hairline `border #2b2b2b` / `border-strong #3d3d3d`, `muted #898989`, `faint #555555`, body `fg #c4c4c4`, emphasis `fg-strong #ededed`.

### Paper (toggle)
A warm cream field with near-black ink. `bg #e9e5db`, `surface #f1eee6`, `elevated #e2ddd0`, hairline `border #a99e86` / `border-strong #7d735c`, `muted #676152`, `faint #847d68`, body `fg #2a2823`, emphasis `fg-strong #15140f`.

### The contrast floor on `muted`

`muted` carries readable secondary text, so it must clear **4.5:1 on the whole neutral
stack** — not just on `bg`. It appears on `surface` (cards), on `surface-2` (strips) and on
`elevated` (the neutral `Badge`), and `elevated` is always the worst case: it is the
backdrop closest in luminance to the text.

Both themes are pinned to that floor. Dark `muted` was `#787878`, which failed everywhere
(`bg` 4.40, `surface` 4.10, `surface-2` 3.86, `elevated` 3.60); `#898989` is the first gray
that clears `elevated` (4.55) and leaves the ramp intact — `muted` 5.56 < `fg` 11.14 <
`fg-strong` 16.60 on `bg`. Paper `muted` was `#6b6555`, which cleared `bg`/`surface` but not
`elevated` (4.28); `#676152` is the same hue 4% darker and clears it (4.54).

**When you change a neutral, re-check `muted` against `elevated`, not against `bg`.**

### The one color
**Danger red** — `#d8593f` (dark) / `#a83a22` (paper). The *only* hue in the system. Used for error messages, destructive actions (delete), and invalid input (e.g. malformed Camelot notation). The one decorative exception: the EQ/waveform loaders (`Equalizer`, `EqMeter`) use danger as a warm accent — peak notch, "hot" trail behind the playhead, playhead and scan border. Outside the loaders, red stays exclusively error/destruction, never a status or quality indicator.

### Named Rules
**The Monochrome Rule.** Nothing carries hue except `danger`. Camelot keys, mix-status, transition quality, risk levels, and provider states are all rendered in neutrals — distinguished by weight, uppercase labels, and position, never by color. There are exactly three documented exceptions, each deliberate and narrow: (1) the `danger` red for errors/destruction; (2) the warm `danger` accent inside the EQ/waveform loaders; and (3) the **Spotify glyph rendered in Spotify green** (`#1DB954`, hover `#1ed760`) on the "open on Spotify" affordance — a brand mark, not a status color. Nothing else earns a hue.

**The One-Red Rule.** Red means error or destruction, except for the intentional warm accent of the EQ/waveform loaders. A low score, a "risky" transition, or a warning state is *not* an error and must stay monochrome.

**The Brand-Green Exception.** The only non-red hue in the system is the Spotify green on the Spotify glyph (the "open on Spotify" link). It is a recognisable brand affordance, scoped strictly to that link — it is never used as a status, quality, or state color anywhere else.

## 3. Typography

**UI font:** IBM Plex Mono (`var(--font-ibm-plex-mono)`, with `ui-monospace, SF Mono, Cascadia Code, Menlo` fallback), loaded via `next/font/google`. It is exposed through a single swappable token `--font-ui` (and aliased to `--font-sans`/`--font-mono`) so a licensed face such as Monument Grotesk Mono can be dropped in by replacing one `.woff2` and one variable.

**Character:** One monospace for everything — brand, headings, labels, body, and data. Personality comes from uppercase tracking on labels and the tabular-figure treatment on metrics, not from a second family.

### Hierarchy
- **Brand** (600, uppercase, `0.16em` tracking): the `CRATORY` wordmark.
- **Page title** (600, uppercase, `0.12em` tracking, `text-sm`): the page title only, rendered by `PageLayout`.
- **Section/card/modal header** (600, uppercase, `0.05em` tracking / `tracking-wider`, base size `1rem`): `CardHeader` and the `Modal` title.
- **Body** (400, `text-sm`, 1.5 line-height): descriptions and prose; cap at ~46–60ch.
- **Label** (500, uppercase, `0.05em` tracking / `tracking-wider`, `~10px`): every column/section header and form-field label.
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
- **Semantic tones** (`primary`/`info`/`success`): the `Badge` component exposes these tones but under the Monochrome Rule they collapse to the neutral rendering — `elevated` + `text-fg` (primary) or `elevated` + `text-muted` (info/success). No hue.
- **Warning:** transparent with a **1px dashed `border-strong` hairline** and `fg` text — attention rendered without hue, borrowing the dashed "provisional" grammar of empty states. For entries that need a second look (an uncertain Shazam match, a download to review), not for plain states. The urgency scale is: neutral fill < dashed ink < danger red.
- **Danger:** transparent with a `danger` border and text. The only colored badge/tone.

### Companion fields and states

- **Alert:** a full-border row; the `danger` tone has a `danger` border and text, the `warning`/`info`/`success` tones have a neutral border and `fg` text (no hue outside danger).
- **Field / Select / Textarea / Checkbox:** same input style (`rounded: 0`, border, `fg` focus ring); `Field` adds an uppercase tracked `~10px` label above the control.
- **KeyBadge:** renders the Camelot in monochrome — a valid key in tabular `fg-strong`, an absent or invalid key in `faint` with a dash. No color for wheel/energy.
- **Track status in Library (icons):** in the Library table the per-row status is no longer a text badge but a group of compact monochrome **icons** with an explanatory `title` — ready for the set = check (`CircleCheck`, `fg-strong`), owned/file on disk = hard drive (`HardDrive`, `fg-strong`), discarded = archive (`Archive`, `faint`). The only chromatic exception is the **Spotify glyph in Spotify green** for the "open on Spotify" link (see The Brand-Green Exception).

### Cards / Containers
- **Background:** `surface` on the `bg` floor; **1px `border` hairline; `radius: 0`; no shadow.**
- **Padding:** the `Card` component applies no padding — the consumer sets it via className. `p-4` (16px) is the recommended default; `p-3` (12px) is allowed for stat-dense cards. Header rows (`CardHeader`) use 20px horizontal (`px-5`), 16px vertical (`py-4`). Prefer hairline-divided sections over nested cards.

### Inputs / Fields (`rounded: 0`)
- **Style:** inset `bg` (darker than the surface) with a 1px `border`, 40px tall; placeholder `faint`.
- **Focus:** border shifts to `border-strong` with a 1px `fg` ring; no layout shift.
- **Error:** `danger` border + a `danger` hint line (e.g. invalid Camelot notation).
- **Field label:** uppercase, tracked, `~10px`, muted, above the control.

### Shell & Navigation — the editorial grammar
- **EditorialShell:** a three-zone, hairline-divided layout. **INDEX** (left, ~180px) holds the `CRATORY` wordmark, tagline, and an uppercase nav (active = underlined) grouped by the flow's stations — *Discover* (Playlists, Discovery, Shazam, Labels), *Collect* (Library, Downloads), *Play* (Sets) — with uppercase `~9px` faint group headers. The footer carries the "Settings" link above a row with the live `HH:MM:SS` clock and the theme toggle. **CONTENT** (center) carries the page's primary object. **MARGINALIA** (right, ~240px, optional per page) carries contextual stats, actions, and notes.
- **PageLayout:** renders the uppercase page title + optional meta over the content, plus the optional marginalia column with its hairline. Below the `lg` breakpoint, INDEX collapses to a horizontal top bar with the groups separated by vertical hairlines, and marginalia drops below the content.

### Progress & Coverage Bars
- **Style:** 8px track on `elevated`, **square** (no radius), `fg` fill. Determinate bars animate width. Indeterminate loading uses no shimmer: it uses the DJ loaders — `Equalizer` (inline EQ with 4 segmented columns) for inline states, the `Loading` pattern (Equalizer + a muted "Loading…" line) for page loads, and `EqMeter` (112-bar pseudo-waveform) for jobs: a numeric value = left→right fill with a playhead, a null value = indeterminate 1.5s scan.

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
