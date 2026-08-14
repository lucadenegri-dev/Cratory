# Product

> **Documento storico, non operativo.** Descrive Sortory quando era
> un'applicazione autonoma. La fusione F1-F6 l'ha assorbita in Cratory come
> sezione `/organize`: per la guida corrente vedi `CLAUDE.md` e `docs/` nella
> radice del repo. Conservato come riferimento sul perché delle scelte.

## Register

product

## Users

A single expert user: a DJ (Luca) preparing his own music library for Rekordbox.
Technical, detail-oriented, works locally on his own machine. Uses Sortory as a
batch tool — sits down to clean a folder of downloads, resolve tag/metadata
issues, accept or reject suggestions, then applies the plan. Bilingual (IT/EN,
default EN). Not a first-time user: he knows the pipeline, so the UI must be fast
and legible, not hand-holding — but it must make clear **what each action does**,
because the destructive/automated actions (AI suggest, provider rescan, bulk
accept) are easy to confuse.

## Product Purpose

Sortory organizes music folders on disk and prepares them for Rekordbox: tag and
metadata cleanup, enrichment from external providers (MusicBrainz/AcoustID,
Discogs, cover-art), file renaming, folder structuring, dedup and quality checks.
It is the single writer of textual tags in the ecosystem. It does not play,
store, or analyze audio.

Success on the **Issues** page: the user can look at a screen full of detected
problems and, with minimal cognitive load, understand each one, see the proposed
fix and how confident it is, and accept/dismiss it — individually or in bulk —
without fear of a silent overwrite. Every action's effect is legible before it
runs.

## Brand Personality

Editorial archive: monospace, monochrome, square (0px radius), ruled filets
instead of cards, tabular numerals. Precise, calm, dense, technical. Shares the
design system with its sibling app *Cratory*. Three words: **precise, editorial,
instrumental**. The tool disappears into the task; no ornament, no delight for
its own sake. Feels like a well-set technical document, not a SaaS dashboard.

## Anti-references

- Consumer music apps (Spotify/Apple Music): colorful, rounded, playful — the opposite.
- Generic SaaS dashboards: hero-metric cards, gradient accents, pill buttons, icon-grid feature blocks.
- Rounded friendly "productivity" UIs (Notion-soft). Sortory is square and ruled.
- Anything that hides what an action does behind a cute label.

## Design Principles

1. **Legibility of consequence.** Before the user clicks, they know what it will
   change and how reversible it is. Automated/bulk actions especially.
2. **Density without noise.** Show a lot at once (it's a batch tool) but with
   clear hierarchy — one clear thing per row, secondary detail subordinated.
3. **No silent overwrites.** Conflicts stay open; precedence
   (manual > cleaned tag > provider > AI) is honored and visible via source +
   confidence markers.
4. **The chrome serves the table.** Filters and actions are means; the list of
   issues is the content. Controls must not out-shout the data.
5. **Match the existing system.** Monospace, monochrome, square, ruled. Reuse
   the committed tokens (`--c-*`) and primitives; branch out only when the UX wins.

## Accessibility & Inclusion

- Respect `prefers-reduced-motion` (already honored by the EQ/waveform loaders).
- Body/interactive text must clear WCAG AA (4.5:1) against its surface in both
  themes (dark default + paper). Avoid faint gray on tinted surfaces for anything
  the user must read to act.
- Bilingual: every user-facing string goes through i18n (`en.ts` source of
  truth, `it.ts` translation).
