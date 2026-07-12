---
target: Ripensiamo il set builder
total_score: 25
p0_count: 0
p1_count: 3
timestamp: 2026-07-09T10-45-43Z
slug: frontend-app-set-builder-page-tsx
---
# Critique — Set Builder

Target: frontend/app/set-builder/page.tsx. Brief: "ripensiamo il set builder."

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Solid phase+timer during gen, but a 1–2 min indeterminate wait with zero partial output; the arc you request is never echoed back |
| 2 | Match System / Real World | 3 | DJ vocabulary fluent, but the result is a flat list, not a timeline — wrong mental model for a set |
| 3 | User Control & Freedom | 1 | Result is read-only. No reorder/swap/lock/regenerate. Regenerating wipes prior set. Alternatives API exists and is unused |
| 4 | Consistency & Standards | 3 | Strong component system; primary CTA meaning governed by a distant checkbox; 4 equal-weight export buttons |
| 5 | Error Prevention | 2 | No input validation; start_bpm > end_bpm allowed under "smooth"; preset vs typed values can contradict |
| 6 | Recognition vs Recall | 3 | Form visible & presets help, but Select has no visible dropdown arrow |
| 7 | Flexibility & Efficiency | 2 | No cmd+Enter; no way to iterate on a result; only 4 hardcoded presets |
| 8 | Aesthetic & Minimalist | 3 | On-brand and non-slop, but form is tall/icon-heavy, ends in two near-identical callouts |
| 9 | Error Recovery | 2 | Errors render as raw String(e) with no recovery path |
| 10 | Help & Documentation | 3 | Prompt-by-example placeholder teaches well; no glossary for first-timer |
| Total | | 25/40 | Acceptable — competent and beautiful, strategically shallow |

## Anti-Patterns Verdict

LLM: Does NOT read as AI-generated — coherent editorial-archive system honoring DESIGN.md. No gradient text/glass/hero-metric/card-grid/side-stripes. Tells that survive: Sparkles used 4+ times (AI cliché glyph); 13 distinct lucide icons on one form pulls against "tipografica, quasi nessun colore."

Deterministic scan: detect.mjs returned [] — zero slop findings. Clean.

Visual overlays: not available. Next.js won't start a second dev instance; live :3000 is the user's and was not injected. No user-visible overlay for this run; CLI scan + source review stand in.

## Overall Impression

Craft is high, aesthetic earned. But the brief says rethink, and the finding is a concept problem, not a paint problem: DESIGN.md principle 5 says "il set builder come composizione, non come compilare un form." It currently IS a form → a read-only receipt. Fill constraints, wait 2 min at a blank indeterminate bar, get back a dead list. No composition moment. Backend already returns transition_score, risk_level, transition_reason, alternative_directions, critical_points, and a /alternatives endpoint (safer|softer|harder|same_artist|surprising) — UI discards nearly all of it. Biggest opportunity: make the RESULT alive.

## What's Working

1. Aesthetic is the product's, not a template's. Detector-clean, on-brand, dense-but-legible. Keep the visual language.
2. Deterministic↔creative spectrum thoughtfully built (form + prompt + AI on/off + technical/creative). Prompt placeholder that shows a good prompt is excellent scaffolding.
3. Preset chips with silent-deactivation-on-edit (clearPreset) — subtle, correct.

## Priority Issues

### [P1] Result is a read-only receipt, not a workbench
Why: DJ's job is iterate the set. Today only iteration = change form, regenerate whole thing, lose everything. Alternatives API + per-position risk_level/transition_reason built but not shipped.
Fix: Make SetTrackRow interactive — per-row swap (via /alternatives popover), lock, reorder (drag), regenerate-from-here; surface transition_reason/risk_level; keep set across regenerations.
Command: /impeccable shape

### [P1] You ask for an arc but never show the arc
Why: Form collects start→end BPM+energy ("Arco del set") but result is a flat list. User must hold requested arc in working memory and diff against numbers. Brand principle #1 = "i numeri sono il linguaggio." EqMeter waveform + tnum already available.
Fix: Compact BPM+energy sparkline/arc atop the result, requested-vs-actual. Set becomes a shape.
Command: /impeccable craft

### [P1] Core data in lowest-contrast, smallest treatment
Why: BPM·Camelot·duration line is text-faint (#555) text-xs ≈ 2.6:1 — fails WCAG AA + 3:1 floor (PRODUCT.md commits to AA). mix_tip and callouts are text-muted (#787878) ≈ 4.4:1 — under 4.5:1 body threshold. Most important info hardest to read.
Fix: Promote BPM/key data to text-muted/text-fg with weight; lift mix_tip to text-fg/text-sm; reserve faint for ancillary marks.
Command: /impeccable audit then /impeccable colorize

### [P2] Primary action has a split brain
Why: Generate button label/behavior governed by "Usa l'AI Set Agent" checkbox on the opposite side of the row, styled like the minor toggles.
Fix: Fuse into a segmented/split primary control ("Genera" / "Genera con AI") at the CTA.
Command: /impeccable layout

### [P2] Select has no dropdown affordance
Why: ui.tsx Select uses appearance-none + pr-8 but renders no chevron. Dropdowns look like plain inputs.
Fix: Add ChevronDown in the reserved pr-8 gutter (system-wide fix in ui.tsx).
Command: /impeccable polish

## Persona Red Flags

Alex (Power User): No cmd+Enter. After 2-min indeterminate wait, gets an untouchable list — no swap/reorder/regenerate-segment. To change one track, re-run whole form and lose the set. Exports to CSV and finishes in a spreadsheet.

Sam (Accessibility): BPM/Camelot at 2.6:1 and mix tips at ~4.4:1 fail promised AA. technical/creative segmented control has no aria-pressed (preset pills do — inconsistent). Arrow-less Select = weak affordance. Final "set ready" arrival not announced.

Crate-digging DJ (project persona): Wants to see the journey and shape it by hand. Instead: arc requested as numbers, returned as list; no swap; exports are Text/CSV/MD but no .m3u/Rekordbox handoff despite Rekordbox being the app's source of truth. Loop back into their real tool is broken.

## Minor Observations

- Two bottom callouts structurally identical — merge or differentiate.
- exported dumps raw <pre> blob inline; feels like debug output.
- Alert shows String(e.message) — can leak HTTP/stack string.
- Sparkles overexposure (4+) — pick one canonical AI moment.
- risk_level, ai_reason, global_explanation, validation.critical_points, alternative_directions all fetched, never rendered.

## Questions to Consider

- If the result were a timeline you compose on, would the up-front form need to be this big? Could the arc be drawn, not typed?
- Backend scores every transition and proposes alternatives per slot. What if "generate" produced a first draft you then conduct — lock, swap, nudge?
- During the 2-min wait, what if tracks streamed in one by one as the engine placed them?
