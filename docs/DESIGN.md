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
  ui-font: "var(--font-mono-ui), ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace"
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
    textTransform: "uppercase"
    padding: "2px 8px"
---

# Product & Design: Cratory

## Product context

### Users

A single DJ — a personal user, self-hosted tool, no multi-tenancy. Usage context:
pre-session preparation. The user has a library of audio files on disk (`LIBRARY_ROOT`, the
source of truth for ownership) and uses streaming playlists and pasted tracklists (Spotify,
SoundCloud, or manual text/CSV import) as leads. They want to index the owned collection,
import BPM/key from Rekordbox or analyze it in-app, build a set, discover missing tracks and
identify them in external mixes, and acquire their files. Text metadata enrichment
(title/artist/album/label/genre) and on-disk tagging happen in the Organize section.

The job to be done: go from "I have these streaming leads and these files on disk" to "I
have a ready set with reasoned transitions, the gaps filled, and the files of owned tracks
on disk".

### Purpose

Cratory is a personal workbench for DJ set preparation. It is not a player, not a social
app. It is the space where the library takes shape: import, normalization, on-disk library
indexing, BPM/key (Rekordbox import or in-app Essentia analysis), file acquisition
(Soulseek/slskd) with an archive and a download review queue, tag and duplicate cleanup on
disk, set building, gap analysis, discovery, exploring the collection by record label, and
mix tracklist identification.

The dashboard opens on a five-stage orientation strip: **Discover** (playlists imported) →
**Acquire** (wishlist, downloads) → **Organize** (files in the inbox) → **Analyze** (BPM/key
still missing) → **Play** (tracks ready for a set). Each stage shows a live count, lights a
dot when it has work pending, and links to its page. Library indexing is not a strip stage:
it runs from the "Index" button at the foot of the left nav, or automatically at startup.

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

1. **Data first, narrative second.** The numbers (BPM, Camelot, energy) are the language.
   Show them with precision and calibrated density. The creative layer (AI, set narrative)
   wraps the data without replacing it.

2. **Every screen pushes forward.** The user has a goal — building a set — so the nav is
   organized as the stations of that flow, not as independent sections: *Discover*
   (Discovery, Shazam, Wishlist) → *Organize* (Files, Issues, Duplicates, Plan, History) →
   *Collect* (Library, Playlists, Labels) → *Play* (Sets, Transitions, Analysis), above a
   standalone Dashboard link. Organize sits between Discover and Collect because that is
   where it lives in the chain: downloaded files get straightened out before they become
   library. The dashboard's pipeline strip tells you where you are in the cycle and what
   comes next.

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

Cratory reads like a printed catalogue of a record library. The interface is monospace
throughout, laid out on a hairline grid, with square geometry and almost no color — ink on a
near-black field by default, or on warm paper when toggled. Density is editorial, not
dashboard-like: dense columns of type, numbered lists, uppercase section labels, and tabular
figures that align like a typeset index.

The system is built from **filets and type**, not fills and shadows. Depth comes from 1px
hairline borders and a tight neutral stack. The only color token in the system is a single
restrained red, reserved for errors and destructive actions. A handful of hues are hardcoded
outside the token set — some deliberate, some deviations the rule does not sanction; they are
enumerated under The Monochrome Rule. Camelot keys, mix status and transition quality are
rendered in monochrome, distinguished by weight, position, and uppercase labels.

This system explicitly rejects: consumer-music-app warmth (soft pastels, oversized rounded
artwork); generic SaaS dashboards (gradients, hero-metric templates, identical card grids);
legacy DJ software density and skeuomorphism; and AI-tool-hype glassmorphism. It is a quiet,
typographic, archival instrument.

**Key characteristics:**
- One monospace (DM Mono) for the entire interface — chrome, labels, body, and data
- Hairline grid: a three-zone editorial shell (INDEX / CONTENT / MARGINALIA) divided by 1px rules
- Square geometry everywhere. `--radius: 0` in the theme means even a bare `rounded`
  compiles to `border-radius: 0`, so squareness is the default you get by accident as well as
  on purpose. Roundness has to be asked for explicitly with `rounded-full`, and only two
  things ask: the pipeline strip's "hot" status dot and the play overlay on cover thumbnails
- Near-monochrome: one `danger` red token, for errors and destructive actions
- Two themes — **dark** (default, near-black) and **paper** (warm cream) — toggled at
  runtime, persisted in `localStorage`, no FOUC (an inline script in `app/layout.tsx` sets
  `data-theme` before first paint)
- Tabular figures (`tnum`) on every metric so numbers align like a typeset index

Where the tokens live: `frontend/app/globals.css` declares the runtime variables `--c-*`
(swapped by `html[data-theme="paper"]`) and maps them to Tailwind utilities through
`@theme inline`. Change a color there, nowhere else.

## 2. Colors

Two monochromatic themes share the same token names. The dark theme is the default (`:root`).

### Dark (default)
A neutral near-black field with light-gray ink. `bg #0d0d0d`, `surface #161616`,
`surface-2 #1c1c1c`, `elevated #222222`, hairline `border #2b2b2b` /
`border-strong #3d3d3d`, `muted #898989`, `faint #555555`, body `fg #c4c4c4`, emphasis
`fg-strong #ededed`.

### Paper (toggle)
A warm cream field with near-black ink. `bg #e9e5db`, `surface #f1eee6`,
`surface-2 #eae6dc`, `elevated #e2ddd0`, hairline `border #a99e86` /
`border-strong #7d735c`, `muted #676152`, `faint #847d68`, body `fg #2a2823`, emphasis
`fg-strong #15140f`.

### The contrast floor on `muted`

`muted` carries readable secondary text, so it must clear **4.5:1 on the whole neutral
stack** — not just on `bg`. It appears on `surface` (cards), on `surface-2` (strips) and on
`elevated` (the neutral `Badge`), and `elevated` is always the worst case: it is the backdrop
closest in luminance to the text.

Both themes are pinned to that floor. Dark `#898989` clears `elevated` at 4.55 and keeps the
ramp intact — `muted` 5.56 < `fg` 11.14 < `fg-strong` 16.60 on `bg`. Paper `#676152` clears
`elevated` at 4.54.

**When you change a neutral, re-check `muted` against `elevated`, not against `bg`.**

`faint` is decorative — icons, hairlines, placeholders, guide text. It does not clear the
floor and must not carry text read at body size.

### The one color token
**Danger red** — `#d8593f` (dark) / `#a83a22` (paper). The only hue in the token set. Used
for error messages, destructive actions (delete), and invalid input (e.g. malformed Camelot
notation). One decorative exception: the DJ loaders (`Equalizer`, `EqMeter`) use `danger` as
a warm accent — the peak notch on the EQ bars, the processed blocks and cursor on the meter.
Outside the loaders, red is exclusively error or destruction, never a status or quality
indicator.

### Named rules

**The Monochrome Rule.** Nothing carries hue except `danger`. Camelot keys, mix status,
transition quality, risk levels and provider states are rendered in neutrals —
distinguished by weight, uppercase labels, and position, never by color.

The rule describes the intent. The code does not fully honour it. These are the hues
hardcoded outside the token set today — found by grepping `#[0-9a-fA-F]{6}` across
`frontend/**/*.{ts,tsx}`, which is the check to re-run before trusting this table:

| Hue | Where | Standing |
|---|---|---|
| Spotify green `#1DB954` / hover `#1ed760` | `track-state-icons.tsx:39`, the "open on Spotify" glyph | brand affordance, deliberate |
| SoundCloud orange `#ff5500` / hover `#ff7700` | `track-state-icons.tsx:50`, the "open on SoundCloud" glyph | brand affordance, deliberate |
| Amber `#b8863f` | `track-state-icons.tsx:25`, the `HardDrive` icon marking an owned file | **open deviation** — a status color, which the rule forbids |
| Olive `#8a8065`, amber `#cfa14a`, terracotta `#d8593f` | `rating-diamond.tsx:9-13`, `RATING_COLORS`, the fill of the rating diamond at levels 1/2/3 | **open deviation, the largest one** — a three-step warm scale encoding a quality judgement, which is the exact thing the rule says never happens |

A brand glyph is a recognisable affordance, not a state; it is scoped strictly to its link
and is never used as a status, quality or state color anywhere else. That reasoning does not
extend to the other two, which encode state and quality directly.

Two things make the rating scale worse than the amber, beyond being a bigger deviation:

- `#d8593f` is the **dark-theme `danger` value copied as a literal** rather than read from
  the token. So it does not theme: on paper, `danger` becomes `#a83a22` and the level-3
  diamond stays dark-theme terracotta. It also silently spends the one color the system
  reserves for errors on a *good* rating — the inverse of what The One-Red Rule means it to
  say.
- It breaks the "components read tokens, never literals" rule in §6, which exists precisely
  to make a theme switch total.

Resolving either deviation is a product decision, not a cleanup: promote the hue to a
documented token with a stated reason, or return the element to the neutral stack. Both are
listed here rather than quietly normalized, so that whoever decides is deciding on the record.

Achromatic exception, for completeness: two cover-art play overlays
(`library-track-grid.tsx:56`, `discovery-lead-grid.tsx:138`) use `bg-black/60` with
`text-white`; only the first darkens to `/80` on hover. Two dimmed backdrops
(`ui.tsx:393` the modal, `organize/issues-table.tsx:81`) use `bg-black/70`. Black and white
scrims over photographic artwork sit outside the neutral token stack but carry no hue, so
the rule is untouched.

**The One-Red Rule.** Red means error or destruction, except for the intentional warm accent
of the DJ loaders. A low score, a "risky" transition, or a warning state is *not* an error
and must stay monochrome.

## 3. Typography

**UI font:** DM Mono, loaded via `next/font/google` at weights 400 and 500 (600 is
synthesized by the browser). It reaches the CSS as `--font-mono-ui`, exposed through a single
swappable token `--font-ui` (aliased to `--font-sans` and `--font-mono`), with
`ui-monospace, SF Mono, Cascadia Code, Menlo` as the fallback stack. A licensed face can be
dropped in by changing that one token.

**Character:** one monospace for everything — brand, headings, labels, body, and data.
Personality comes from uppercase tracking on labels and the tabular-figure treatment on
metrics, not from a second family.

### Hierarchy
- **Brand** (600, uppercase, `0.16em` tracking): the `CRATORY` wordmark.
- **Page title** (600, uppercase, `0.12em` tracking, `text-sm`): the page title only, rendered by `PageLayout`.
- **Section/card/modal header** (600, uppercase, `tracking-wider`, base size `1rem`): `CardHeader` and the `Modal` title.
- **Nav group header** (600, uppercase, `0.14em` tracking, `9px`, `fg-strong`): the four station groups in INDEX.
- **Body** (400, `text-sm`, 1.5 line-height): descriptions and prose; cap at ~46–60ch.
- **Label** (500, uppercase, `tracking-wider`, `10px`): every column/section header and form-field label.
- **Data** (400, `font-variant-numeric: tabular-nums`): every BPM, Camelot key, energy, duration, and count, via the `.tnum` utility.

### Named rules
**The Tabular Rule.** Every number a DJ scans is set in tabular figures (`.tnum`) so columns
align like a typeset index.

**The Mono Rule.** One monospace family for the entire UI. No serif headlines, no second
sans "for contrast" — hierarchy is weight, size, case, and tracking.

## 4. Elevation

Flat by definition. Depth on the page is conveyed entirely by **hairline borders and the
neutral stack** (`bg → surface → surface-2 → elevated`). No surface — card, panel, strip,
table, modal — carries a shadow: the modal separates from the page with a hairline border and
a dimmed (not blurred) `bg-black/70` backdrop.

The one place a shadow is allowed is a **floating layer that overlaps content it does not
own**: dropdown menus, the playlist filter menu, and the rating tooltip use `shadow-lg` on an
`elevated` panel with a hairline border. That is a z-order cue, not decoration.

### Named rule
**The Hairline Rule.** Structure is drawn with 1px borders. If a region needs separating, add
a filet or step the tonal stack — never a shadow, never a radius. Shadows are for things that
float above the page, nothing else.

## 5. Components

Shared primitives live in `frontend/components/ui.tsx`.

### Buttons (`rounded: 0`, uppercase, tracked)
- **Primary:** solid `fg-strong` fill, `bg`-colored ink, hover softens to `fg`. The single loudest action on a screen.
- **Outline:** transparent, `border-strong` edge, foreground text; hover fills to `elevated`.
- **Ghost:** transparent, muted text; hover fills to `elevated`. For low-emphasis/icon actions.
- **Danger:** transparent with a `danger` border and text; hover inverts to a `danger` fill. Destructive actions only.
- **Sizes:** `md` = 40px tall, `px-4`; `sm` = 32px tall, `px-3`. Both `text-xs`.
- **Focus:** 1px `fg` ring. Disabled drops to 50% opacity.

`ButtonLink` reuses the same variant and size maps for anchor elements.

### Badges (`rounded: 0`, uppercase, tracked, `10px`)
- **Neutral:** `elevated` background, `muted` text. The default and near-universal badge — platform tags, statuses, transition classes, risk levels.
- **Semantic tones** (`primary` / `info` / `success`): exposed by the `Badge` component but collapsed to the neutral rendering under the Monochrome Rule — `elevated` + `text-fg` (primary) or `elevated` + `text-muted` (info/success). No hue.
- **Warning:** transparent with a **1px dashed `border-strong` hairline** and `fg` text — attention rendered without hue, borrowing the dashed "provisional" grammar of empty states. For entries that need a second look (an uncertain Shazam match, a download to review), not for plain states. Urgency scale: neutral fill < dashed ink < danger red.
- **Danger:** transparent with a `danger` border and text. The only colored badge.

### Companion fields and states

- **Alert:** a full-border row with `role="alert"` (danger) or `role="status"` (everything else), so screen readers announce it. The `danger` tone has a `danger` border and text; `warning` / `info` / `success` all render with a neutral border and `fg` text.
- **Input / Textarea / Select / Checkbox:** one shared style (`rounded: 0`, `bg` inset, 1px `border`, `fg` focus ring). `Input` and `Select` are 40px tall; `Select` carries a `faint` chevron. **Field** wraps a control with an uppercase tracked `10px` label above it and an optional hint below.
- **SegmentedControl / Chip / Combobox / DropdownMenu:** the compact controls for filters and pickers, same square hairline grammar.
- **KeyBadge:** renders the Camelot in monochrome — a valid key (1–12 + A/B) in tabular `fg-strong`, an absent or malformed key in `faint` with a dash. No color for wheel or energy.
- **Track status icons (`TrackStateIcons`):** the per-row status in Library and playlist detail is a group of compact icons with an explanatory `title`, not text badges — play control, ready-for-set = `CircleCheck` (`fg-strong`), owned file = `HardDrive`, discarded = `Archive` (`faint`), plus the Spotify and SoundCloud "open on" glyphs. See the hue table under The Monochrome Rule.
- **RatingDiamond:** the 1–3 personal rating, rendered as a `polygon` diamond — unrated is an outlined `currentColor` diamond, a rating fills it. Clicking opens a small popover of the three levels, anchored above-right and outside the row's flow, on an `elevated` panel with a hairline and `shadow-lg` (a floating layer, per §4). The fill colors are the system's largest open deviation — see the hue table under The Monochrome Rule.

### Cards / containers
- **Background:** `surface` on the `bg` floor; **1px `border` hairline, `radius: 0`, no shadow.**
- **Padding:** the `Card` component applies none — the consumer sets it. `p-4` (16px) is the recommended default; `p-3` (12px) is allowed for stat-dense cards. `CardHeader` uses `px-5` / `py-4` and closes with a hairline. Prefer hairline-divided sections over nested cards.

### Shell & navigation — the editorial grammar
- **EditorialShell:** a two-column hairline grid — **INDEX** (left, 180px, sticky and
  independently scrollable) and **CONTENT**. INDEX holds the `CRATORY` wordmark, the tagline,
  and the uppercase nav (active item underlined) grouped into the four stations, then a
  footer stack: the "Index" library-scan button, the "Settings" link, and a row with the live
  `HH:MM:SS` clock and the theme toggle. The Wishlist entry carries a tabular count of
  downloads waiting to be fixed. Below `lg`, INDEX collapses to a horizontal top bar with the
  groups separated by vertical hairlines.
- **PageLayout:** renders the uppercase page title, optional `meta` and a right-aligned
  `action` above the content, plus an optional **MARGINALIA** column (right, 240px) that
  opens when a page supplies `marginalia` (contextual stats and actions) or `guide`
  (explanatory text, used by the Organize pages). Below `lg` the marginalia drops beneath the
  content.

### Progress, coverage and loading
- **Determinate bars:** 8px track on `elevated`, **square**, `fg` fill, animated width.
- **`Equalizer`:** the inline loader — four segmented columns animating at different periods, each with a warm `danger` peak notch. Exported as `Spinner` for compatibility.
- **`Loading`:** the standard page-load treatment — `Equalizer` plus a muted "Loading…" line.
- **`EqMeter`:** the job meter, styled like a terminal progress bar — `danger` blocks over a light dither, with a blinking cursor in the next slot while work is in flight. A numeric `value` fills left to right; `value = null` is an indeterminate advancing block train; `calm` (static ratios, e.g. coverage) drops the cursor and all motion.
- No shimmer anywhere.

### Modal
- **Style:** `fixed inset-0`, `z-50`, dimmed `bg-black/70` backdrop (no blur); `surface` panel with a `border-strong` hairline, `radius: 0`, no shadow. Two widths (`md` / `lg`). Header with title + `×`, optional right-aligned footer actions. Escape closes; the panel takes focus on open only, never on re-render.
- **Doctrine:** modals are the exception. Used for focused edits (manual track values, rename, delete confirmation, file linking).

### Empty states
- **Style:** dashed `border` container, centered `faint` icon + `fg-strong` title + one muted line + a single action. Teaches the next step in the flow.

## 6. Do's and don'ts

### Do:
- **Do** keep the entire UI monospace; hierarchy is weight, case, and tracking.
- **Do** draw structure with 1px hairlines and the neutral stack — flat, square.
- **Do** set every metric in tabular figures (`.tnum`).
- **Do** render Camelot keys, mix status, and quality/risk in monochrome.
- **Do** keep both themes in sync — every surface must read correctly in dark *and* paper.
- **Do** use uppercase tracked labels for column/section headers and field labels.
- **Do** change colors in `globals.css` only; components read tokens, never literals.

### Don't:
- **Don't** introduce any color other than `danger`, and only for errors/destruction.
- **Don't** add rounded corners; `radius: 0` (The Hairline Rule). Write `rounded-none` when
  you want to be explicit — that is what 43 of the 44 square call sites do. A bare `rounded`
  also renders square here, but it reads like an intent to round: the one occurrence
  (`rating-diamond.tsx:81`) is worth normalizing.
- **Don't** put a shadow on a surface — only on a layer that floats over content.
- **Don't** color-code keys or mix quality (The Monochrome Rule).
- **Don't** introduce a second type family or a non-mono face in UI chrome (The Mono Rule).
- **Don't** treat a low score or "risky" transition as an error — keep it monochrome (The One-Red Rule).
- **Don't** put `faint` on anything that must be read at body size; use `muted` for readable secondary text.
