# SetArc Rebrand "Editorial Archive" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SetArc's frontend identity with an editorial/archive aesthetic (monospace, hairline grid, square geometry, near-monochrome, dark default + paper toggle) while preserving all behavior.

**Architecture:** Identity flows through four centralized layers, rebuilt in order: (1) design tokens + runtime theme in `globals.css`/`layout.tsx`, (2) an editorial shell (`IndexNav` + `EditorialShell` + `PageLayout` + `Clock` + `ThemeToggle`) replacing the sidebar, (3) the shared primitives in `ui.tsx` + `key-badge.tsx`, (4) each of the 17 page routes restyled via a shared playbook. No framework change.

**Tech Stack:** Next.js 16, React 19, Tailwind v4 (`@theme inline` runtime theming), `next/font/google` (IBM Plex Mono), lucide-react.

**Spec:** `docs/superpowers/specs/2026-06-21-setarc-rebrand-design.md`

## Global Constraints

- **No framework/library changes.** Next 16 / React 19 / Tailwind v4 / lucide-react only.
- **No behavioral changes.** Pure presentation. Preserve all data-loading, props, state, routes, and copy.
- **Monochrome only.** The single permitted color is `danger` (errors + destructive actions). No `info`/`warning`/`success`/`primary` colors anywhere.
- **Square geometry.** `--radius: 0px`. No `rounded-*` except `rounded-none`. No shadows (only modal backdrop dim, no blur).
- **Font:** IBM Plex Mono everywhere via the single token `--font-ui`. No Geist.
- **Theme:** default dark (no attribute); `html[data-theme="paper"]` = paper; persisted in `localStorage["setarc-theme"]`; no FOUC.
- **Verification (no test framework exists):** every task ends with `cd frontend && npm run lint` (zero errors) and `npm run build` (clean). Page tasks additionally require a visual check in both themes.
- **Commit style:** do NOT add Claude as co-author. Conventional commit messages.

### Color tokens (exact, confirmed)

| Token (`--color-*` / utility) | Dark (`:root`) | Paper (`[data-theme=paper]`) |
|---|---|---|
| `bg`         | `#0d0d0d` | `#e9e5db` |
| `surface`    | `#161616` | `#f1eee6` |
| `surface-2`  | `#1c1c1c` | `#eae6dc` |
| `elevated`   | `#222222` | `#e2ddd0` |
| `border`     | `#2b2b2b` | `#cdc7b8` |
| `border-strong` | `#3d3d3d` | `#b2ab99` |
| `muted`      | `#787878` | `#86806f` |
| `faint`      | `#555555` | `#a79f8d` |
| `fg`         | `#c4c4c4` | `#2a2823` |
| `fg-strong`  | `#ededed` | `#15140f` |
| `danger`     | `#d8593f` | `#a83a22` |

### Restyle Playbook (applies to EVERY page task)

Apply these exact substitutions to className strings and inline JSX. This table IS the page-restyle spec; each page task references it.

| Old (current) | New |
|---|---|
| `bg-primary` (CTA fills) | replace the element with the `<Button>` primitive, or `bg-fg-strong text-bg` |
| `text-primary-fg` | `text-bg` |
| `text-primary` | `text-fg-strong` |
| `bg-primary-hover` / `hover:bg-primary-hover` | `hover:bg-fg` |
| `bg-primary/15`, `bg-primary/[0.04]`, `bg-primary/70` | fills: `bg-elevated`; bar fills: `bg-fg` |
| `border-primary/30` | `border-border` |
| `text-info` (links) | `text-fg hover:underline underline-offset-4` |
| `bg-info/15 text-info` (chips) | `<Badge>` (neutral) |
| `text-warning`, `text-success`, `bg-warning/*`, `bg-success/*` | `text-muted` (text) / `bg-elevated` (fills) |
| `rounded-lg`, `rounded-xl`, `rounded-md`, `rounded-full`, `rounded-[var(--radius)]` | `rounded-none` |
| `shadow-2xl`, `shadow-*` | remove |
| decorative icon tinted with accent (`text-primary` on icon) | `text-muted` (or remove icon if non-functional) |

Then wrap the page body in `<PageLayout>` (Task 6) and move contextual blocks into its `marginalia` per spec §8. Numbered lists use `tnum` and `01, 02…` formatting where the spec calls for editorial lists.

---

## Task 1: Design tokens + runtime theme + font

**Files:**
- Modify: `frontend/app/globals.css` (full rewrite of the `@theme` block and base styles)
- Modify: `frontend/app/layout.tsx` (font + html attrs; shell wiring done in Task 5)

**Interfaces:**
- Produces: utility classes `bg-bg bg-surface bg-surface-2 bg-elevated border-border border-border-strong text-muted text-faint text-fg text-fg-strong text-danger bg-fg-strong bg-danger`; `--radius: 0px`; font token `--font-ui`; runtime theming via `html[data-theme="paper"]`.

- [ ] **Step 1: Rewrite `frontend/app/globals.css`**

```css
@import "tailwindcss";

/* Design system "editorial archive": monospace, monocromo, filetti, squadrato.
   I valori vivono nelle variabili runtime --c-* (commutate da data-theme);
   @theme inline mappa le utility Tailwind a quelle variabili. */
@theme inline {
  --color-bg: var(--c-bg);
  --color-surface: var(--c-surface);
  --color-surface-2: var(--c-surface-2);
  --color-elevated: var(--c-elevated);
  --color-border: var(--c-border);
  --color-border-strong: var(--c-border-strong);
  --color-muted: var(--c-muted);
  --color-faint: var(--c-faint);
  --color-fg: var(--c-fg);
  --color-fg-strong: var(--c-fg-strong);
  --color-danger: var(--c-danger);

  --radius: 0px;

  --font-ui: var(--font-ibm-plex-mono), ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
  --font-sans: var(--font-ui);
  --font-mono: var(--font-ui);
}

/* Dark = default (nessun attributo) */
:root {
  --c-bg: #0d0d0d;
  --c-surface: #161616;
  --c-surface-2: #1c1c1c;
  --c-elevated: #222222;
  --c-border: #2b2b2b;
  --c-border-strong: #3d3d3d;
  --c-muted: #787878;
  --c-faint: #555555;
  --c-fg: #c4c4c4;
  --c-fg-strong: #ededed;
  --c-danger: #d8593f;
}

/* Paper = toggle */
html[data-theme="paper"] {
  --c-bg: #e9e5db;
  --c-surface: #f1eee6;
  --c-surface-2: #eae6dc;
  --c-elevated: #e2ddd0;
  --c-border: #cdc7b8;
  --c-border-strong: #b2ab99;
  --c-muted: #86806f;
  --c-faint: #a79f8d;
  --c-fg: #2a2823;
  --c-fg-strong: #15140f;
  --c-danger: #a83a22;
}

html, body { height: 100%; }

body {
  background-color: var(--color-bg);
  color: var(--color-fg);
  font-family: var(--font-ui);
  -webkit-font-smoothing: antialiased;
}

/* numeri tabellari per BPM, key, durate */
.tnum {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

/* scrollbar discreta */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--color-border-strong) transparent;
}
*::-webkit-scrollbar { width: 10px; height: 10px; }
*::-webkit-scrollbar-thumb { background: var(--color-border-strong); border: 2px solid var(--color-bg); }

@keyframes shimmer {
  0% { opacity: 0.55; }
  50% { opacity: 1; }
  100% { opacity: 0.55; }
}
.animate-shimmer { animation: shimmer 1.6s ease-in-out infinite; }
```

- [ ] **Step 2: Swap the font in `frontend/app/layout.tsx`**

Replace the two Geist imports and the consts. New top of file (leave the rest of the file for Task 5):

```tsx
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SetArc",
  description: "AI DJ set builder, discovery and library analysis",
};
```

Update the `<html>` tag's className to use the new variable (the body/shell is rewritten in Task 5, but make it compile now):

```tsx
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`}>
      <body className="h-full">{children}</body>
    </html>
  );
}
```

- [ ] **Step 3: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero lint errors; build completes. (Pages still reference old color utilities like `bg-primary` — Tailwind v4 silently drops unknown utilities, so the build is clean; those are fixed in Tasks 7+.)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/globals.css frontend/app/layout.tsx
git commit -m "feat(ui): editorial tokens, runtime dark/paper theme, IBM Plex Mono"
```

---

## Task 2: Clock component

**Files:**
- Create: `frontend/components/clock.tsx`

**Interfaces:**
- Produces: `Clock` — `() => JSX.Element`, a live `HH:MM:SS` readout (echo of the moodboard timestamp). Renders `--:--:--` until mounted (avoids hydration mismatch).

- [ ] **Step 1: Create `frontend/components/clock.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

export function Clock() {
  const [time, setTime] = useState<string>("--:--:--");

  useEffect(() => {
    const fmt = () => new Date().toLocaleTimeString("it-IT", { hour12: false });
    setTime(fmt());
    const id = setInterval(() => setTime(fmt()), 1000);
    return () => clearInterval(id);
  }, []);

  return <span className="tnum text-faint">{time}</span>;
}
```

- [ ] **Step 2: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/clock.tsx
git commit -m "feat(ui): live clock readout for editorial shell"
```

---

## Task 3: Theme toggle

**Files:**
- Create: `frontend/components/theme-toggle.tsx`

**Interfaces:**
- Consumes: `localStorage["setarc-theme"]` with values `"dark" | "paper"`; `html[data-theme]` attribute.
- Produces: `ThemeToggle` — `() => JSX.Element`. Reads stored theme on mount, toggles `data-theme` + persists.

- [ ] **Step 1: Create `frontend/components/theme-toggle.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "paper";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("setarc-theme") as Theme | null) ?? "dark";
    setTheme(stored);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "paper" : "dark";
    setTheme(next);
    localStorage.setItem("setarc-theme", next);
    if (next === "paper") {
      document.documentElement.setAttribute("data-theme", "paper");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  };

  return (
    <button
      onClick={toggle}
      aria-label="Cambia tema"
      className="inline-flex items-center gap-1.5 uppercase tracking-wider text-muted transition-colors hover:text-fg"
    >
      <span aria-hidden>◑</span>
      {theme === "dark" ? "Paper" : "Dark"}
    </button>
  );
}
```

- [ ] **Step 2: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/theme-toggle.tsx
git commit -m "feat(ui): dark/paper theme toggle with persistence"
```

---

## Task 4: INDEX navigation column

**Files:**
- Create: `frontend/components/index-nav.tsx`

**Interfaces:**
- Consumes: `Clock` (Task 2), `ThemeToggle` (Task 3), `cn` from `@/lib/cn`.
- Produces: `IndexNav` — `() => JSX.Element`. Wordmark + tagline + uppercase nav (active = underlined) + footer (clock + toggle). Vertical layout on `lg`, horizontal top bar below `lg`.

- [ ] **Step 1: Create `frontend/components/index-nav.tsx`**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { Clock } from "./clock";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/playlists", label: "Playlist" },
  { href: "/library", label: "Libreria" },
  { href: "/labels", label: "Etichette" },
  { href: "/discovery", label: "Discovery" },
  { href: "/shazam", label: "Shazam" },
  { href: "/sets", label: "Set" },
  { href: "/settings", label: "Impostazioni" },
];

export function IndexNav() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block">
        <Link href="/" className="block text-sm font-semibold tracking-[0.16em] text-fg-strong">SETARC</Link>
        <p className="hidden text-[10px] uppercase tracking-wider text-muted lg:mt-1 lg:block">Workbench per DJ set</p>
        <div className="text-[10px] lg:hidden"><ThemeToggle /></div>
      </div>

      <ul className="flex gap-4 overflow-x-auto px-4 pb-3 lg:flex-1 lg:flex-col lg:gap-0 lg:overflow-visible lg:pb-0">
        {NAV.map(({ href, label }) => (
          <li key={href} className="shrink-0">
            <Link
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cn(
                "block whitespace-nowrap py-1 text-xs uppercase tracking-wider transition-colors",
                isActive(href) ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg",
              )}
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden items-center justify-between gap-2 px-4 py-3 text-[10px] lg:flex">
        <Clock />
        <ThemeToggle />
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/index-nav.tsx
git commit -m "feat(ui): editorial INDEX navigation column"
```

---

## Task 5: Editorial shell + no-FOUC + remove sidebar

**Files:**
- Create: `frontend/components/editorial-shell.tsx`
- Modify: `frontend/app/layout.tsx` (wire shell + no-FOUC script)
- Delete: `frontend/components/sidebar.tsx`

**Interfaces:**
- Consumes: `IndexNav` (Task 4).
- Produces: `EditorialShell` — `({ children }: { children: ReactNode }) => JSX.Element`. Renders the INDEX column (left on `lg`, top bar below) + scrolling main area.

- [ ] **Step 1: Create `frontend/components/editorial-shell.tsx`**

```tsx
import type { ReactNode } from "react";
import { IndexNav } from "./index-nav";

export function EditorialShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[180px_1fr]">
      <aside className="border-b border-border lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <IndexNav />
      </aside>
      <main className="min-w-0">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Finalize `frontend/app/layout.tsx`**

Replace the `RootLayout` function (keep the Task 1 imports/metadata at top) with:

```tsx
import { EditorialShell } from "@/components/editorial-shell";

const NO_FOUC = `(function(){try{var t=localStorage.getItem('setarc-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`}>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        <EditorialShell>{children}</EditorialShell>
      </body>
    </html>
  );
}
```

(The `import { EditorialShell }` line goes with the other imports at the top of the file; shown here for clarity.)

- [ ] **Step 3: Delete the old sidebar**

```bash
git rm frontend/components/sidebar.tsx
```

- [ ] **Step 4: Verify lint + build + visual**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. Then `npm run dev`, open `http://localhost:3000`, confirm: INDEX column on the left with `SETARC` wordmark, nav, live clock, and a working dark/paper toggle (toggle persists across reload, no flash).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/layout.tsx frontend/components/editorial-shell.tsx
git commit -m "feat(ui): editorial shell, no-FOUC theme bootstrap, drop sidebar"
```

---

## Task 6: PageLayout (content + marginalia grammar)

**Files:**
- Create: `frontend/components/page-layout.tsx`

**Interfaces:**
- Produces: `PageLayout` — `({ title, meta?, marginalia?, marginaliaTitle?, children }: { title: string; meta?: ReactNode; marginalia?: ReactNode; marginaliaTitle?: string; children: ReactNode }) => JSX.Element`. Renders an uppercase page header (title + optional meta) over the content; optional right marginalia column with hairline (collapses below content on small screens). When `marginalia` is omitted, content is full width.

- [ ] **Step 1: Create `frontend/components/page-layout.tsx`**

```tsx
import type { ReactNode } from "react";

export function PageLayout({
  title,
  meta,
  marginalia,
  marginaliaTitle,
  children,
}: {
  title: string;
  meta?: ReactNode;
  marginalia?: ReactNode;
  marginaliaTitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={marginalia ? "lg:grid lg:grid-cols-[1fr_240px]" : ""}>
      <section className="min-w-0 px-5 py-5 lg:px-6 lg:py-6">
        <header className="mb-5 flex items-baseline gap-3 border-b border-border pb-3">
          <h1 className="text-sm font-semibold uppercase tracking-[0.12em] text-fg-strong">{title}</h1>
          {meta != null && <span className="tnum text-xs text-muted">{meta}</span>}
        </header>
        {children}
      </section>
      {marginalia && (
        <aside className="border-t border-border px-5 py-5 lg:border-l lg:border-t-0 lg:py-6">
          {marginaliaTitle && (
            <div className="mb-3 text-[10px] uppercase tracking-wider text-muted">{marginaliaTitle}</div>
          )}
          {marginalia}
        </aside>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/page-layout.tsx
git commit -m "feat(ui): PageLayout editorial content + marginalia grammar"
```

---

## Task 7: Rewrite primitives (`ui.tsx`)

**Files:**
- Modify: `frontend/components/ui.tsx` (full rewrite, same public exports/props)

**Interfaces:**
- Consumes: `cn` from `@/lib/cn`, `X` from lucide-react.
- Produces: same exports as today — `Card, CardHeader, Button, Input, Textarea, Select, Field, Checkbox, Badge, Progress, Spinner, EmptyState, Modal, Alert`. Same prop signatures (`Button` variants `primary|outline|ghost|danger`, sizes `sm|md`; `Badge` tone `neutral|primary|info|warning|danger|success` — tones other than `danger` render neutral; `Alert` tone `danger|warning|info|success` — non-danger render neutral). Square, monochrome.

- [ ] **Step 1: Rewrite `frontend/components/ui.tsx`**

```tsx
"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

/* ---------------------------------------------------------------- Card */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("border border-border bg-surface", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h3 className="font-semibold uppercase tracking-wider text-fg-strong">{title}</h3>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/* -------------------------------------------------------------- Button */

type Variant = "primary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md";

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 font-medium uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg";
const BTN_VARIANT: Record<Variant, string> = {
  primary: "bg-fg-strong text-bg hover:bg-fg",
  outline: "border border-border-strong bg-transparent text-fg hover:bg-elevated",
  ghost: "bg-transparent text-muted hover:bg-elevated hover:text-fg",
  danger: "border border-danger bg-transparent text-danger hover:bg-danger hover:text-bg",
};
const BTN_SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-xs",
};

export function Button({
  variant = "primary", size = "md", className, children, ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button className={cn(BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size], className)} {...props}>
      {children}
    </button>
  );
}

/* --------------------------------------------------------------- Inputs */

const FIELD =
  "w-full border border-border bg-bg px-3 text-sm text-fg placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-1 focus:ring-fg";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(FIELD, "py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(FIELD, "h-10 cursor-pointer appearance-none bg-bg pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Checkbox({ label, checked, onChange, disabled }: {
  label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean;
}) {
  return (
    <label className={cn("flex items-center gap-2 text-sm", disabled ? "text-faint" : "cursor-pointer text-fg")}>
      <input
        type="checkbox" checked={checked} disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-[var(--color-fg)]"
      />
      {label}
    </label>
  );
}

/* ---------------------------------------------------------------- Badge */

type Tone = "neutral" | "primary" | "info" | "warning" | "danger" | "success";
const BADGE_TONE: Record<Tone, string> = {
  neutral: "bg-elevated text-muted",
  primary: "bg-elevated text-fg",
  info: "bg-elevated text-muted",
  warning: "bg-elevated text-muted",
  danger: "border border-danger text-danger",
  success: "bg-elevated text-muted",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider", BADGE_TONE[tone], className)}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------- Progress bar */

export function Progress({ value }: { value: number | null }) {
  const indeterminate = value == null;
  return (
    <div className="h-2 w-full overflow-hidden bg-elevated">
      <div
        className={cn("h-full bg-fg transition-all", indeterminate && "w-1/3 animate-shimmer")}
        style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-block animate-spin rounded-full border-2 border-border-strong border-t-fg", className ?? "h-4 w-4")} />
  );
}

/* ----------------------------------------------------------- Empty / msg */

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center border border-dashed border-border px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <p className="font-medium text-fg-strong">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- Modal */

export function Modal({ open, onClose, title, children, footer, size = "md" }: {
  open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; footer?: ReactNode;
  size?: "md" | "lg";
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-black/70 p-4 pt-[10vh]"
      onClick={onClose}
    >
      <div
        className={cn("w-full border border-border-strong bg-surface", size === "lg" ? "max-w-lg" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3.5">
            <h3 className="font-semibold uppercase tracking-wider text-fg-strong">{title}</h3>
            <button onClick={onClose} className="text-faint transition-colors hover:text-fg"><X size={18} /></button>
          </div>
        )}
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "warning" | "info" | "success"; children: ReactNode }) {
  const isDanger = tone === "danger";
  return (
    <div className={cn(
      "border px-4 py-3 text-sm",
      isDanger ? "border-danger text-danger" : "border-border text-fg",
    )}>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Verify lint + build + visual**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. Then `npm run dev` and open `http://localhost:3000` (dashboard still uses old direct color classes; primitives like cards/buttons/badges should already render square + monochrome).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/ui.tsx
git commit -m "feat(ui): square monochrome primitives (single danger red)"
```

---

## Task 8: Monochrome KeyBadge

**Files:**
- Modify: `frontend/components/key-badge.tsx` (full rewrite)

**Interfaces:**
- Produces: `KeyBadge` — `({ camelot, className }: { camelot: string | null; className?: string }) => JSX.Element`. Renders the Camelot value as tabular monospace text; absent/invalid → `—` in `faint`. No color.

- [ ] **Step 1: Rewrite `frontend/components/key-badge.tsx`**

```tsx
// Camelot key reso in monocromatico: nessuna tinta inventata.
// Chiave assente o non valida → trattino neutro.

const CAMELOT_RE = /^\s*(\d{1,2})\s*([ABab])\s*$/;

export function KeyBadge({ camelot, className }: { camelot: string | null; className?: string }) {
  const m = camelot ? CAMELOT_RE.exec(camelot) : null;
  const number = m ? Number(m[1]) : null;

  if (!m || number == null || number < 1 || number > 12) {
    return <span className={`text-faint ${className ?? ""}`}>{camelot ?? "—"}</span>;
  }

  const label = `${m[1]}${m[2].toUpperCase()}`;
  return <span className={`tnum font-medium text-fg-strong ${className ?? ""}`}>{label}</span>;
}
```

- [ ] **Step 2: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/key-badge.tsx
git commit -m "feat(ui): monochrome KeyBadge"
```

---

## Task 9: Restyle Dashboard (`app/page.tsx`)

**Files:**
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `PageLayout` (Task 6), restyled primitives (Task 7). Preserve all data hooks (`apiGet`, `getLabels`), `recommend()`, and copy.

- [ ] **Step 1: Apply the Restyle Playbook + PageLayout**

Edits (preserve all logic/data/copy):
1. Wrap the returned tree in `<PageLayout title="DASHBOARD" meta={stats ? `${stats.total_tracks} TRACCE` : undefined} marginaliaTitle="LIBRERIA" marginalia={<>…</>}>`. Move the **Range BPM + Tonalità più frequenti** card and the **Top etichette** card into `marginalia`. Keep stats grid, "Prossimo passo", "Azioni rapide", and "Copertura enrichment" in the content column. Remove the old `<header>` block (PageLayout renders the title).
2. In `Stat`: replace `Card className="p-4"` stays; change `accent ? "text-primary" : ""` → `accent ? "text-fg-strong" : ""`; the label `text-muted` stays.
3. In `Action`: `rounded-[var(--radius)]` → `rounded-none`; icon chip `bg-primary/15 text-primary` → `bg-elevated text-muted`; `rounded-lg` → `rounded-none`; keep hover `hover:border-border-strong hover:bg-elevated/40`.
4. In `Coverage` / `KeyDistribution` / `LabelBars`: bar track `bg-elevated` stays; fill `bg-primary/70` → `bg-fg`; `rounded-full` (track + fill) → `rounded-none`; remove the `text-primary` on numbers (use `text-muted`).
5. Empty-state inline link: replace `bg-primary px-4 py-2 text-sm font-medium text-primary-fg hover:bg-primary-hover rounded-lg` with `bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg hover:bg-fg`.
6. "Prossimo passo" card: `border-primary/30 bg-primary/[0.04]` → `border-border`; icon chip `bg-primary/15 text-primary rounded-xl` → `bg-elevated text-muted rounded-none`; `<Badge tone="primary">` stays (renders neutral).
7. Enrichment links `text-info hover:underline` → `text-fg hover:underline underline-offset-4`; `text-info` on "Tutte le etichette"/"Arricchisci" → same.
8. Error alert: keep `<Alert tone="danger">`.

- [ ] **Step 2: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. Then `npm run dev`, open `/`, toggle dark↔paper. Confirm: no lime/blue anywhere, square cards, monochrome bars, error state (stop the backend to trigger) shows the single red.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): editorial dashboard"
```

---

## Task 10: Restyle Library + Track detail

**Files:**
- Modify: `frontend/app/library/page.tsx`
- Modify: `frontend/app/tracks/[id]/page.tsx`

**Interfaces:**
- Consumes: `PageLayout`, restyled primitives, `KeyBadge`.

- [ ] **Step 1: Read both files, then apply Restyle Playbook + PageLayout**

For `library/page.tsx`:
1. Wrap in `<PageLayout title="LIBRERIA" meta={`${total} TRACCE`} marginaliaTitle="FILTRI" marginalia={<>…filters/counts…</>}>` — move the filter controls (key/bpm/source) and any coverage counts into `marginalia`; the track table stays in content.
2. Convert the track table to the editorial table style: `border-collapse`, `th`/`td` with `border-b border-border px-2 py-1.5`, `th` uppercase `text-[10px] tracking-wider text-muted font-normal`; add a leading numbered column `01, 02…` (`tnum text-muted`) if a stable index is available from the existing map.
3. Apply every row of the Restyle Playbook to remaining classes.

For `tracks/[id]/page.tsx`:
1. Wrap in `<PageLayout title="TRACCIA" meta={track?.title} marginaliaTitle="ENRICHMENT" marginalia={<>…source/confidence + edit action…</>}>`.
2. Apply the Restyle Playbook. Keep `enrichment_source`/`enrichment_confidence` displays (text only).

- [ ] **Step 2: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. `npm run dev`, open `/library` and a `/tracks/<id>`, toggle themes, confirm monochrome + square + hairline tables.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/library/page.tsx frontend/app/tracks/[id]/page.tsx
git commit -m "feat(ui): editorial library + track detail"
```

---

## Task 11: Restyle Playlists area

**Files:**
- Modify: `frontend/app/playlists/page.tsx`
- Modify: `frontend/app/playlists/[id]/page.tsx`
- Modify: `frontend/app/playlists/import-spotify/page.tsx`
- Modify: `frontend/app/playlists/import-manual/page.tsx`

**Interfaces:**
- Consumes: `PageLayout`, restyled primitives, `KeyBadge`.

- [ ] **Step 1: Read all four files, then apply Restyle Playbook + PageLayout**

- `playlists/page.tsx`: `<PageLayout title="PLAYLIST" meta={`${count}`} marginaliaTitle="SORGENTE" marginalia={<>…per-source counts, last sync, import action…</>}>`. Render the list as an editorial numbered list (`01, 02…`, `tnum`).
- `playlists/[id]/page.tsx`: `<PageLayout title="PLAYLIST" meta={playlist?.name} marginaliaTitle="DETTAGLI" marginalia={<>…source, duration, avg bpm, sync/delete actions…</>}>`. Tracklist as hairline table.
- `playlists/import-spotify/page.tsx`: `<PageLayout title="IMPORT — SPOTIFY" marginaliaTitle="NOTE" marginalia={<>…help on Spotify data scope…</>}>`. Form via `Field`/`Input`/`Button`.
- `playlists/import-manual/page.tsx`: `<PageLayout title="IMPORT — MANUALE" marginaliaTitle="FORMATO" marginalia={<>…format help + count preview…</>}>`.
- Apply the Restyle Playbook to all four. Use `<Button variant="danger">` for any delete action.

- [ ] **Step 2: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. `npm run dev`, walk `/playlists`, a detail, and both import pages in both themes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/playlists
git commit -m "feat(ui): editorial playlists area"
```

---

## Task 12: Restyle Sets + Set Builder + Transitions

**Files:**
- Modify: `frontend/app/sets/page.tsx`
- Modify: `frontend/app/sets/[id]/page.tsx`
- Modify: `frontend/app/set-builder/page.tsx`
- Modify: `frontend/app/transitions/page.tsx`

**Interfaces:**
- Consumes: `PageLayout`, restyled primitives, `KeyBadge`.

- [ ] **Step 1: Read all four files, then apply Restyle Playbook + PageLayout**

- `sets/page.tsx`: `<PageLayout title="SET" meta={`${count}`} marginaliaTitle="AZIONI" marginalia={<>…new set action, counts…</>}>`. Numbered editorial list.
- `sets/[id]/page.tsx`: `<PageLayout title="SET" meta={set?.name} marginaliaTitle="DETTAGLI" marginalia={<>…meta, validated AI notes, export/delete…</>}>`. Tracklist + transitions as hairline tables.
- `set-builder/page.tsx`: `<PageLayout title="SET BUILDER" marginaliaTitle="VINCOLI" marginalia={<>…parameters, validation state…</>}>`. Candidate + draft areas in content.
- `transitions/page.tsx`: `<PageLayout title="TRANSIZIONI" marginaliaTitle="LEGENDA" marginalia={<>…textual monochrome legend…</>}>`. Hairline table.
- Apply the Restyle Playbook. Any mix-status indicators must be monochrome (text + weight), never colored.

- [ ] **Step 2: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. `npm run dev`, walk `/sets`, a set detail, `/set-builder`, `/transitions` in both themes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/sets frontend/app/set-builder frontend/app/transitions
git commit -m "feat(ui): editorial sets, set builder, transitions"
```

---

## Task 13: Restyle Labels + Discovery + Shazam

**Files:**
- Modify: `frontend/app/labels/page.tsx`
- Modify: `frontend/app/labels/[label]/page.tsx`
- Modify: `frontend/app/discovery/page.tsx`
- Modify: `frontend/app/shazam/page.tsx`
- Modify: `frontend/app/shazam/[id]/page.tsx`

**Interfaces:**
- Consumes: `PageLayout`, restyled primitives, `KeyBadge`.

- [ ] **Step 1: Read all five files, then apply Restyle Playbook + PageLayout**

- `labels/page.tsx`: `<PageLayout title="ETICHETTE" meta={`${count}`} marginaliaTitle="ORDINA" marginalia={<>…totals, sort…</>}>`. Numbered editorial list; label bars use `bg-fg` fills, square.
- `labels/[label]/page.tsx`: `<PageLayout title="ETICHETTA" meta={label} marginaliaTitle="STATISTICHE" marginalia={<>…label stats…</>}>`. Hairline track table.
- `discovery/page.tsx`: `<PageLayout title="DISCOVERY" marginaliaTitle="FILTRI" marginalia={<>…sources/filters + ranking explanation…</>}>`. Ranked results in content.
- `shazam/page.tsx`: `<PageLayout title="SHAZAM" marginaliaTitle="STATO" marginalia={<>…job state, help…</>}>`. Identifications list.
- `shazam/[id]/page.tsx`: `<PageLayout title="IDENTIFICAZIONE" marginaliaTitle="META" marginalia={<>…source, confidence…</>}>`. Identified tracklist.
- Apply the Restyle Playbook to all five.

- [ ] **Step 2: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. `npm run dev`, walk `/labels`, a label detail, `/discovery`, `/shazam`, a shazam detail in both themes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/labels frontend/app/discovery frontend/app/shazam
git commit -m "feat(ui): editorial labels, discovery, shazam"
```

---

## Task 14: Restyle Settings + Track Edit Modal + accent sweep

**Files:**
- Modify: `frontend/app/settings/page.tsx`
- Modify: `frontend/components/track-edit-modal.tsx`

**Interfaces:**
- Consumes: `PageLayout`, restyled primitives.

- [ ] **Step 1: Read both files, then apply Restyle Playbook**

- `settings/page.tsx`: `<PageLayout title="IMPOSTAZIONI" marginaliaTitle="AIUTO" marginalia={<>…field descriptions/help…</>}>`. Forms via `Field`/`Input`/`Select`/`Button`.
- `track-edit-modal.tsx`: apply the Restyle Playbook; ensure it uses `Modal`, `Field`, `Input`, `Button` primitives; delete/destructive uses `<Button variant="danger">`; no `accent-[var(--color-primary)]` (use the rewritten `Checkbox`).

- [ ] **Step 2: Final accent sweep — confirm no stale color utilities remain**

Run (matches color *utilities* only, so it won't trip on the `"primary"` variant names inside `ui.tsx`):
```bash
cd frontend && grep -rEn "(bg|text|border|ring|from|via|to)-(primary|info|success|warning)|primary-(fg|hover)|rounded-(lg|xl|md|full)|shadow-(sm|md|lg|xl|2xl)" app components
```
Expected: **no output**. If any line prints, fix it per the Restyle Playbook (this catches anything missed in Tasks 9–14). `accent-[var(--color-fg)]` and `rounded-none` are allowed and won't match.

- [ ] **Step 3: Verify lint + build + visual (both themes)**

Run: `cd frontend && npm run lint && npm run build`
Expected: zero errors; clean build. `npm run dev`, open `/settings`, open a track-edit modal, toggle themes.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/settings/page.tsx frontend/components/track-edit-modal.tsx
git commit -m "feat(ui): editorial settings + track-edit modal; final accent sweep"
```

---

## Task 15: Regenerate design-system docs

**Files:**
- Modify: `DESIGN.md` (repo root)
- Modify: `.impeccable/design.json` (repo root)
- Replace: `frontend/public/logo.png` usage already removed (Task 5); no file change needed unless referenced elsewhere.

**Interfaces:**
- Consumes: final tokens (Task 1), primitives (Task 7).

- [ ] **Step 1: Update `DESIGN.md` frontmatter + body**

Rewrite the `colors`, `typography`, `rounded`, and `components` sections of `DESIGN.md` to match the new system: name "SetArc — Editorial Archive", the Task 1 color values (document dark as canonical, note the paper theme), `fontFamily` = `"IBM Plex Mono, ui-monospace, monospace"`, `rounded` all `0px`, and component descriptions matching the square/monochrome primitives. Remove all lime/signal-color references.

- [ ] **Step 2: Update `.impeccable/design.json`**

Mirror the same values in `.impeccable/design.json`: replace `colorMeta` canonical values + ramps with the monochrome scale + single `danger`; set typography to IBM Plex Mono; update each `components[*].css` snippet to square/monochrome (no `border-radius`, no lime, single red for danger). Remove `info`/`warning`/`success` color metas (or repoint to neutral).

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run build`
Expected: clean build (docs don't affect build; this confirms nothing regressed). Visually skim both docs for any remaining `#c2f24a`/`primary`/`lime` references:
```bash
grep -rEn "c2f24a|lime|Geist|rounded.*0\.7rem|primary-hover" DESIGN.md .impeccable/design.json
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add DESIGN.md .impeccable/design.json
git commit -m "docs: regenerate design system for editorial archive rebrand"
```

---

## Self-Review

**Spec coverage:**
- §2 stack invariato → Global Constraints + Task 1 (no framework change). ✓
- §3.1 monocromo / §3.2 single red → Restyle Playbook + Tasks 7, 8, 9–14. ✓
- §3.3 dark default + paper toggle + no-FOUC → Tasks 1, 3, 5. ✓
- §3.4 IBM Plex Mono swappable token → Task 1 (`--font-ui`). ✓
- §3.5 square / no shadow → Task 1 (`--radius:0`) + Task 7 + Playbook. ✓
- §3.6 minimal editorial icons → Playbook (icon rows) + Tasks 9–14. ✓
- §3.7 bespoke per-page → Task 6 grammar + Tasks 9–14 PageLayout. ✓
- §4 exact tokens → Task 1 table (verbatim). ✓
- §5 type scale → Task 1 (`--font-ui`) + uppercase tracked labels in Tasks 6, 7. ✓
- §6 layout grammar (INDEX/CONTENT/MARGINALIA, clock, toggle, responsive, wordmark not logo.png) → Tasks 2–6. ✓
- §7 primitives + KeyBadge + track-edit-modal → Tasks 7, 8, 14. ✓
- §8 marginalia per page → Tasks 9–14 (titles/content specified per page). ✓
- §9 chrome (clock, toggle, no-FOUC, scrollbar) → Tasks 1, 2, 3, 5. ✓
- §10 testing (lint+build+visual both themes) → every task. ✓
- §12 regenerate DESIGN.md/design.json → Task 15. ✓

**Placeholder scan:** Core tasks (1–8, 15) contain complete code. Page tasks (9–14) are mechanical transformations governed by the exact Restyle Playbook table + per-page PageLayout signatures + a grep gate (Task 14 Step 2) that fails the work if any stale color utility remains — no vague "handle styling" left open.

**Type consistency:** `PageLayout` signature defined once (Task 6) and consumed with matching props in Tasks 9–14. `Button`/`Badge`/`Alert` prop unions preserved from the original `ui.tsx` (Task 7) so pages compile unchanged. `KeyBadge` signature unchanged (Task 8). Token utility names (`text-fg-strong`, `bg-fg-strong`, `bg-elevated`, `border-border`, `text-danger`) defined in Task 1 and used consistently throughout.
