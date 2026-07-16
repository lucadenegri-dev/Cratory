---
target: barra di caricamento di tutto il programma
total_score: 27
p0_count: 0
p1_count: 2
timestamp: 2026-07-12T00-20-14Z
slug: frontend-components-ui-tsx-loading-bars
---
# Critique — the loading bar, program-wide

Target resolved to the loading/progress family (not one file):
- `Progress` (ui.tsx:134): flat 2px bar, solid bg-fg fill — only dashboard coverage stats (page.tsx:40)
- `EqMeter` (ui.tsx:182): 112-bar rekordbox waveform, hot danger head, breathing — global job bar (jobs-provider.tsx:245), set-builder
- `Equalizer`/`Loading` (ui.tsx:143/160): 4-bar animated EQ + muted label — ~16 page-load spots
- `GlobalProgress` (jobs-provider.tsx:198): fixed bottom bar hosting EqMeter rows

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Strong overall; flat Progress no ARIA, remaining track near-invisible |
| 2 | Match System / Real World | 4 | Waveform + hot head is a perfect DJ/rekordbox metaphor |
| 3 | User Control and Freedom | 2 | No cancel/dismiss on running jobs from the bar |
| 4 | Consistency and Standards | 2 | Two unrelated bar languages for the same "% complete" concept |
| 5 | Error Prevention | 3 | Both primitives clamp 0–100 defensively |
| 6 | Recognition Rather Than Recall | 3 | Job rows carry label + detail + %; indeterminate ··· is cryptic |
| 7 | Flexibility and Efficiency | 2 | No collapse/expand, no retry, "+N more" is a dead end |
| 8 | Aesthetic and Minimalist | 3 | EqMeter beautiful but maximalist against a hairline design system |
| 9 | Error Recovery | 3 | Job error shows detail in danger; no retry affordance |
| 10 | Help and Documentation | 2 | No hint explaining indeterminate state |
| Total | | 27/40 | Acceptable — solid, distinctive foundation with real gaps |

## Anti-Patterns Verdict
Not AI slop — EqMeter is a genuine domain signature (rekordbox waveform + danger playhead). Deterministic waveform, SSR-safe, reduced-motion handled for .eq and .eqm. detect.mjs on ui.tsx/jobs-provider.tsx/page.tsx returned []. Browser overlay not run (bars gated on live backend/job states).

## What's Working
1. Domain-perfect metaphor (EqMeter, ui.tsx:182) — waveform + danger playhead = scrubbing a track.
2. Persistent bottom job bar (jobs-provider.tsx:210) — fixed + in-flow spacer, survives navigation.
3. Reduced-motion is real (globals.css:110–114).

## Priority Issues

[P1] Two divergent progress-bar languages for one concept. Progress (flat solid bg-fg) vs EqMeter (waveform) both = "% complete", zero shared DNA. Fix: decide static-ratio vs live-process axis deliberately (quiet non-animated waveform variant for coverage) or retire Progress and use EqMeter everywhere. Command: /impeccable distill

[P1] Flat Progress bar invisible to assistive tech. EqMeter has role=progressbar + aria-valuenow/min/max (ui.tsx:190–194); Progress (ui.tsx:134) has none. Fix: add matching ARIA + aria-label. Command: /impeccable harden

[P2] Determinate meter never stops breathing + remaining is a ghost. Lit bars run eqmBreathe even at exact value (globals.css:102); off track is --c-border on bg-surface (~1.3:1 dark). Fix: reserve breathe for hot zone; lift off track toward border-strong. Command: /impeccable animate

[P2] Continuous infinite animation at scale. 112 spans/row, infinite eqmBreathe, up to MAX_ROWS rows pinned to every page. transition-all on Progress (ui.tsx:137) should be transition-[width]. Fix: animate only hot zone; pause on hidden tab. Command: /impeccable optimize

[P3] Indeterminate reads as stalled. Static text-faint ··· (jobs-provider.tsx:255). Fix: inline Equalizer / animated ellipsis. Command: /impeccable clarify

## Persona Red Flags
- Sam (a11y): Progress announces nothing; indeterminate relies on visual scan; no aria-live for completion.
- Alex (power): no cancel/pause/dismiss from bar; "+N more" can't expand.
- Riley (stress): determinate value visibly wobbles; error outcome has no retry.

## Minor Observations
- Spinner=Equalizer alias (ui.tsx:156) — migrate new code to Equalizer.
- Loader labels text-muted; paper theme #86806f on #e9e5db ~3.6:1, under 4.5:1.
- Loading hardcodes py-8; feels loose in table cells / modals.

## Questions to Consider
- Is flat vs waveform split intentional (static ratio vs live process) or just unmigrated legacy?
- Should a settled exact percentage animate at all?
- What would a cancel affordance on the job bar cost?
