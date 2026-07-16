---
target: pagina Analisi (frontend/app/analysis/page.tsx)
total_score: 17
p0_count: 2
p1_count: 3
timestamp: 2026-07-16T21-11-18Z
slug: frontend-app-analysis-page-tsx
---
# Critique — /analysis (frontend/app/analysis/page.tsx)

Live state at review: `owned=412, ready_for_set=411, missing_bpm=1, missing_key=1, analyzed=57, divergent=0, rekordbox_pending=1`.

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Coverage renders **100%** while `missing_bpm=1` (`Math.round(411/412)`). Zero `aria-live` regions on the page (verified in browser). |
| 2 | Match System / Real World | 2 | Table prints the raw backend enum `(rekordbox)`; `sourceManual/Rekordbox/Cratory` i18n keys exist and are used nowhere. |
| 3 | User Control and Freedom | 1 | No select-all. The safe bulk apply `mode:"divergent"` exists at `routers/analysis.py:88` and is unreachable from the UI. |
| 4 | Consistency and Standards | 2 | Bypasses `CardHeader` (9 other pages use it), `Checkbox`, `Button`. Ignores the `marginalia` slot. |
| 5 | Error Prevention | 3 | Genuinely strong 4-layer overwrite safety — but the red button is armed at `divergent=0`. |
| 6 | Recognition Rather Than Recall | 1 | `manual > rekordbox > cratory` precedence is never stated in the UI. |
| 7 | Flexibility and Efficiency | 1 | No select-all, no sort/filter, no "apply all divergent". |
| 8 | Aesthetic and Minimalist Design | 2 | 12 numbers before the first verb; a 112-bar meter restating text 4px above it. |
| 9 | Error Recovery | 1 | `engineUnavailable` copy written in EN+IT and never wired; 503 surfaces as a raw backend string. |
| 10 | Help and Documentation | 2 | `startedNote` explains the safety model *after* the click. |
| **Total** | | **17/40** | **Poor — the IA needs an overhaul; the visual system does not** |

## Anti-Patterns Verdict

**Deterministic scan**: `detect.mjs` on `page.tsx` + `rekordbox-import-card.tsx` returned `[]`, exit 0. Clean. No slop tells at the pixel level.

**LLM assessment**: The styling is earned and disciplined — mono throughout, hairlines, `radius:0`, no shadows, one red. Nobody would flag the CSS. The **composition** is the problem, and it hits DESIGN.md's own anti-reference verbatim ("Generic SaaS dashboard: identical cards, hero-metric templates"): 6-metric tile row → progress bar → stacked identical feature cards. Layout equals component order — every feature got a card, every stat got a tile, so nothing was ranked. This is AI scaffolding wearing a monospace coat. The detector cannot see this; it only reads decoration.

## What's Working

1. **The overwrite-safety chain is real engineering.** Four independent layers: the frontend `manualCount` gate that only interrupts when manual values are genuinely at risk; `protectedCount` from the live selection; the backend `422 analysis_force_required`; and the 1-decimal comparison in `_apply` that makes `128.0 vs 128.04` analyzer noise a no-op so `bpm_source` isn't silently demoted `rekordbox → cratory`. Someone understood that provenance is data.
2. **The copy is the best thing on the page.** `forceConfirm` names blast radius, magnitude, and irreversibility in one line without apologizing. `overwriteLabel` explains the consequence, not the mechanism. This is DESIGN.md's "confident, precise, does not apologize" tone, landed — and wasted at 10px muted.
3. **Monochrome discipline holds under pressure.** A page with `divergent`/`missing`/`weak` states is exactly where red-amber-green leaks in. It didn't.

## Priority Issues

### [P0] The red button is armed when there's nothing to shoot; the safe bulk action has no button
- **What**: `disabled={busy || (overview?.analyzed ?? 0) === 0}` (page.tsx:227) gates FORCE APPLY ALL on *analyzed*, not *divergent*. At `analyzed=57, divergent=0` the browser confirms `disabled:false` — red, live, guarded by "cannot be undone", and provably a no-op (`applied=0 · skipped=57`). Meanwhile `POST /analysis/apply {mode:"divergent"}` is implemented at `routers/analysis.py:88` and never called; `page.tsx:110` only ever sends `mode:"all"`.
- **Why it matters**: The page offers the two worst options (nuclear, or N individual clicks) and hides the correct one. Training the user that the red modal is a no-op destroys the one warning that will matter the day divergences exist.
- **Fix**: Gate force on `divergent > 0`. Promote `mode:"divergent"` to primary: `APPLY ALL DIVERGENT (N)`. Demote force to a ghost link inside the card body. At `divergent=0` collapse the card to one muted line — no heading, no buttons.
- **Suggested command**: `/impeccable shape`

### [P0] No hierarchy exists, mechanically
- **What**: `<h2 className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-muted">` (page.tsx:181, 188, 213). Browser-verified: the three section headings compute to **12px, `rgb(107,101,85)` muted** — smaller than the 14px page title and no louder than the 10px tile labels above them. `text-fg-strong` appears only on tile values. Five `<Card>`s in `space-y-6`, zero announced.
- **Why it matters**: This is the literal mechanism of "confusionaria". Every text element lands in the same 10–12px uppercase muted band, so the eye finds no anchor and re-reads everything.
- **Fix**: Use `CardHeader` (`text-fg-strong`, `border-b`, `px-5 py-4`) for all sections, as the other 9 pages do. Then create rank: Rekordbox is primary; in-app analysis becomes a hairline-divided section inside it, not a peer card.
- **Suggested command**: `/impeccable layout`

### [P1] Two input methods presented as peers, contradicting the project's own rule
- **What**: CLAUDE.md rule 2 makes Rekordbox **primary** and in-app analysis the **alternative**. The page renders them as identical stacked cards with three unrelated vocabularies for one concept: a checkbox ("Overwrite existing"), a select ("Scope"), and a red button ("Force apply all"). Worse, the select is *safely misleading*: `scope="all"` only analyzes; `auto_apply_missing` fills empties only. "All owned tracks" is completely safe and reads as dangerous, one card above a red button that genuinely is.
- **Why it matters**: The user cannot answer "which do I use?" or "what happens if I run both?"
- **Fix**: One card, `BPM / KEY SOURCES`, stating the hierarchy `manual > rekordbox > cratory`. Rekordbox first. In-app below a hairline, framed as "for what Rekordbox didn't cover". Add a hint under the select: "Analysis never overwrites — it only fills empty fields. Conflicts appear in Divergences." Say it *before* the click.
- **Suggested command**: `/impeccable shape`

### [P1] The tiles don't earn their space, and the coverage meter lies
- **What**: `missing_bpm=1`, `missing_key=1`, `rekordbox_pending=1` are **the same track** under three names. `ready_for_set=411` is `owned − 1`, derivable. `coveragePct` rounds 99.75 → **100%**. 12 numbers, ~4 facts.
- **Why it matters**: The user can't tell whether they have 1 problem or 3, and the single loudest visual on the page — a full 112-bar meter — asserts a completion that is false.
- **Fix**: Cut to 3 tiles: `OWNED 412`, `NOT READY 1`, `CONFLICTS 0`. Make `NOT READY` a link to that track. Move the by-source footnote and coverage into `marginalia` (the slot `PageLayout` already exposes, used by 10 pages). Use `Math.floor`, and never render 100% while `missing_bpm + missing_key > 0`.
- **Suggested command**: `/impeccable distill`

### [P1] Accessibility: the page's primary control is unnamed, and nothing is announced
- **What**: Browser-verified. The file input (`rekordbox-import-card.tsx:46`) has **no accessible name**: no `aria-label`, no wrapping label, no `id`+`for`, `labels` empty. Screen reader says "file upload, button". The page has **zero** `aria-live`/`role=status`/`role=alert` regions, so "Analysis started" and every error are silent. The per-row Apply (page.tsx:291) is a raw `<button>` that bypasses `BTN_BASE` and has **no focus ring** — keyboard users get no visible focus on the control that writes data.
- **Why it matters**: DESIGN.md commits to WCAG AA. Also verified: the by-source footnote (`text-faint` 11px) is **3.54:1 in paper and 2.43:1 in dark** against its surface — both fail the 4.5:1 minimum, and dark is the default theme. This is DESIGN.md's own Don't ("Don't put `faint` on anything that must be read at body size").
- **Fix**: Wrap the file input in a labelled `Field` or give it `aria-label`; add `role="status"` to `Alert`; route the row action through `Button`; move the footnote from `faint` to `muted`.
- **Suggested command**: `/impeccable harden`

### [P2] The current-value cell hides half its own provenance
- **What**: `page.tsx:273` — `{(r.bpm_source ?? r.key_source) && (<span>({r.bpm_source ?? r.key_source})</span>)}`. One source label for two values. If `bpm_source="rekordbox"` and `key_source="manual"`, the row shows `(rekordbox)` and conceals that the key is a manual correction — while `isProtected` (line 93) correctly counts both, so the badge can warn about manual values the row doesn't show.
- **Why it matters**: Provenance is the entire safety model of this page, and the highest-authority source is the one that can vanish from the display.
- **Fix**: Render per value — `128.0 (rekordbox) · 8A (manual)` — via the already-written, currently orphaned `sourceManual/sourceRekordbox/sourceCratory` keys. Wire `engineUnavailable` to the 503.
- **Suggested command**: `/impeccable clarify`

## Persona Red Flags

**Alex (power user)**: The page never says what to do — six tiles, no verb. The one actionable item is discoverable only by computing `owned − ready_for_set = 1`, and there is no link to that track anywhere. The meter says 100%, so he concludes "done" and leaves. The only bulk button is a guaranteed no-op today. No select-all exists in the codebase; `toggle()` is per-id only. He scrolls past a status report to reach a file input every visit.

**Sam (accessibility/keyboard)**: The file input — the page's primary control — has no accessible name (verified). Zero aria-live regions, so success and error notices are silent; they also render at the top of the page while the buttons that fire them are 2–3 cards down. The per-row Apply has no focus ring. The protected-count warning is `tone="warning"` → `bg-elevated text-muted` at 10px, i.e. the quietest text on the page sits beside the loudest button. 2N tab stops through the table with no select-all. Heading outline is inconsistent: this page's `<h2>` vs `CardHeader`'s `<h3>`.

## Minor Observations

- The `Upload` icon (rekordbox-import-card.tsx:79) is 16px, faint, `aria-hidden`, floated right, next to a file input that already says upload. Pure decoration.
- The scope select is **clipped**: verified `scrollWidth 239 > clientWidth 222` at `w-56`, so "Only tracks missing BPM/key" renders as "Only tracks missing B…".
- The bare `input[type=file]` cannot be localized (the UA supplies "Choose File" from browser locale) and cannot match the design system's button vocabulary.
- `compatWeak` uses `tone="danger"` — a divergent key is a conflict, not an error; arguably a One-Red-Rule violation that further dilutes the force button's signal.
- `/analysis` sits in the **Play** nav group, but DESIGN.md's flow makes Analyze⤴ its own stage between Organize and Play. Filed under its destination, not its function.
- `compatUnknown: "—"` renders an em-dash inside an uppercase badge that says nothing.

## Questions to Consider

1. **Will the Divergences table ever have rows?** `auto_apply_missing` fills empties; Rekordbox import fills the rest; `_apply` treats sub-0.1 BPM deltas as no-ops. Divergences only appear if you analyze a track that already has a value — i.e. only via `scope="all"`, which is not the default. If `divergent=0` is the steady state, this page spends its entire lower third, and its only red, on a case that structurally almost never occurs — and the live data agrees.
2. **Should this page exist?** Strip the redundant tiles, the meter, and the empty divergences card and what remains is a file input, a select, and a button. Is "Analysis" a page, or a leftover boundary from `dashboard/pipeline.tsx` — where `RekordboxImportCard` came from, and whose `t.dashboard.*` keys it still uses?
3. **The page's job is "make owned tracks ready for set". 411 of 412 are ready. Why does it open with six numbers instead of the one track that isn't?**
