# Product

> Strategic layer only (who / what / why). The visual system — tokens, typography,
> components, named rules — lives in [`DESIGN.md`](DESIGN.md), which remains the
> source of truth for *how it looks*. This file distills the product half of that
> document so design tooling can read register and principles without parsing the
> whole design system.

## Register

product

## Users

A single DJ. Personal, self-hosted, single-user tool — no multi-tenancy, no public
surface. The usage context is pre-session preparation at a desk: streaming playlists
and pasted tracklists as leads, a library of audio files on disk as the source of
truth for ownership.

The job to be done: go from "I have these streaming leads and these files on disk" to
"I have a ready set with reasoned transitions, the gaps filled, and the files of owned
tracks on disk".

## Product Purpose

Cratory is a workbench for DJ set preparation: import and normalization, on-disk
library indexing, BPM/key (Rekordbox import or in-app Essentia analysis), file
acquisition (Soulseek/slskd) with an archive and a download review queue, tag and
duplicate cleanup, set building, gap analysis, discovery, label exploration, and mix
tracklist identification.

It is not a player, not a deck, not a social app. Success = the user enters with raw
playlists and leaves with a structured, annotated set, a list of tracks to add, and
their files acquired into the library.

## Brand Personality

Sober, typographic, archival.

Cratory reads like a printed catalogue of a record collection: monospace everywhere, a
hairline grid, square geometry, almost no color. Crate digging is a creative act and
there is energy in it — but the energy is rendered with density, weight and
typographic hierarchy, never with color.

Tone: confident without arrogance, precise without coldness. Opinionated and
unapologetic about it. Quiet, not shy.

## Anti-references

- **Consumer music app** (Spotify, Apple Music): soft, rounded, built for passive
  listening. Cratory is a work tool, not a jukebox.
- **Generic SaaS dashboard**: identical card grids, purple/teal gradients,
  hero-metric templates, everything centered. AI scaffolding visible from a mile away.
- **Legacy DJ software** (Traktor, Rekordbox): information overload, 2000s UX, heavy
  rather than navigable.
- **AI-tool hype**: pastel gradients, huge rounded cards, glassmorphism. Not to be
  confused with the deliberate **paper** theme — warm cream with near-black ink,
  1px hairlines, square geometry.

## Design Principles

1. **Data first, narrative second.** The numbers (BPM, Camelot, energy) are the
   language. The creative layer wraps the data, never replaces it.
2. **Every screen pushes forward.** The nav is the stations of one flow (Discover →
   Organize → Collect → Play), not a set of independent sections. Every page should
   make the next step obvious.
3. **Dense but breathable.** DJ data is dense; the interface carries it without
   collapsing into a spreadsheet. Deliberate spacing, semantic grouping, clear
   hierarchy.
4. **Opinionated, not decorative.** Every visual choice must feel made for this tool.
   Hierarchy comes from weight, case, tracking and tabular figures — not from color.
5. **Experimental energy.** Discovery should feel like digging through crates; the set
   builder like composition, not form-filling.

## Accessibility & Inclusion

WCAG AA on text contrast (≥ 4.5:1 body, ≥ 3:1 large text) — enforced on the whole
neutral stack, with `muted` checked against `elevated` rather than `bg`. No further
requirement beyond contrast (single user). Motion honours `prefers-reduced-motion`
where implemented.
