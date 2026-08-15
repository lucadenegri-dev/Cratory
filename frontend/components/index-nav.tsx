"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { RefreshCw, Settings } from "lucide-react";
import { cn } from "@/lib/cn";
import { downloadPending, startLibraryIndex } from "@/lib/api";
import { useT, type Dictionary } from "@/lib/i18n";
import { Clock } from "./clock";
import { ThemeToggle } from "./theme-toggle";

/* Il menu racconta la sequenza del flusso: Scopri → Colleziona → Organizza →
   Suona. Colleziona sta fra Scopri e Organizza: prima la libreria e le sue
   liste, poi il lavoro sui file. */
const navGroups = (t: Dictionary): { title: string | null; items: { href: string; label: string }[] }[] => [
  { title: null, items: [{ href: "/", label: t.nav.dashboard }] },
  {
    title: t.nav.groupDiscover,
    items: [
      { href: "/discovery", label: t.nav.discovery },
      { href: "/shazam", label: t.nav.shazam },
      { href: "/wishlist", label: t.nav.downloads },
    ],
  },
  {
    title: t.nav.groupCollect,
    items: [
      { href: "/library", label: t.nav.library },
      { href: "/playlists", label: t.nav.playlists },
      { href: "/labels", label: t.nav.labels },
    ],
  },
  {
    title: t.nav.groupOrganize,
    items: [
      { href: "/organize/files", label: t.organize.nav.files },
      { href: "/organize/issues", label: t.organize.nav.issues },
      { href: "/organize/duplicates", label: t.organize.nav.duplicates },
      { href: "/organize/plan", label: t.organize.nav.plan },
      { href: "/organize/history", label: t.organize.nav.history },
    ],
  },
  {
    title: t.nav.groupPlay,
    items: [
      { href: "/sets", label: t.nav.sets },
      { href: "/transitions", label: t.nav.transitions },
      { href: "/analysis", label: t.nav.analysis },
    ],
  },
];

export function IndexNav() {
  const t = useT();
  const NAV_GROUPS = navGroups(t);
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  // Conteggio "da sistemare" sulla voce Download (l'archivio separato non esiste più).
  const [pendingCount, setPendingCount] = useState(0);
  useEffect(() => {
    let live = true;
    downloadPending()
      .then((rows) => { if (live) setPendingCount(rows.length); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [pathname]);  // rivaluta a ogni navigazione (es. dopo aver sistemato tracce)

  /* Indicizza LIBRARY_ROOT: il disco è la libreria. Il job gira in background
     lato server; qui mostriamo solo l'avvio (409 = LIBRARY_ROOT mancante o job
     già in corso → torniamo a idle senza rumore). */
  const [scan, setScan] = useState<"idle" | "busy" | "done">("idle");
  const runIndex = async () => {
    if (scan === "busy") return;
    setScan("busy");
    try {
      await startLibraryIndex();
      setScan("done");
      setTimeout(() => setScan("idle"), 4000);
    } catch {
      setScan("idle");
    }
  };
  const scanLabel = scan === "busy" ? t.nav.indexStarting : scan === "done" ? t.nav.indexStarted : t.nav.index;

  return (
    <nav className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block">
        <Link href="/" className="block text-sm font-semibold tracking-[0.16em] text-fg-strong">CRATORY</Link>
        <p className="hidden text-[10px] uppercase tracking-wider text-muted lg:mt-1 lg:block">{t.nav.tagline}</p>
        <div className="flex items-center gap-3 text-[10px] lg:hidden">
          <Link href="/settings" aria-label={t.nav.settings} aria-current={isActive("/settings") ? "page" : undefined} className={cn("transition-colors hover:text-fg", isActive("/settings") ? "text-fg-strong" : "text-muted")}><Settings size={14} /></Link>
          <ThemeToggle />
        </div>
      </div>

      <div className="flex gap-4 overflow-x-auto px-4 pb-3 lg:flex-1 lg:flex-col lg:gap-0 lg:overflow-visible lg:pb-0">
        {NAV_GROUPS.map((g, gi) => (
          <div
            key={g.title ?? "root"}
            className={cn("flex shrink-0 gap-4 lg:block", gi > 0 && "border-l border-border pl-4 lg:border-l-0 lg:pl-0")}
          >
            {g.title && (
              <div className="hidden lg:mb-1 lg:mt-4 lg:block text-[9px] font-semibold uppercase tracking-[0.14em] text-fg-strong">
                {g.title}
              </div>
            )}
            <ul className="flex gap-4 lg:flex-col lg:gap-0">
              {g.items.map(({ href, label }) => (
                <li key={href} className="shrink-0">
                  <Link
                    href={href}
                    aria-current={isActive(href) ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-1.5 whitespace-nowrap py-1 text-xs uppercase tracking-wider transition-colors",
                      isActive(href) ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg",
                    )}
                  >
                    {label}
                    {href === "/wishlist" && pendingCount > 0 && (
                      <span className="tnum text-[10px] text-faint">({pendingCount})</span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="hidden lg:block">
        <button
          type="button"
          onClick={runIndex}
          disabled={scan === "busy"}
          className={cn(
            "flex w-full items-center gap-2 border-t border-border px-4 py-2.5 text-left text-xs uppercase tracking-wider transition-colors disabled:cursor-default",
            scan === "done" ? "text-fg-strong" : "text-muted hover:text-fg",
          )}
        >
          <RefreshCw size={13} className={cn("shrink-0", scan === "busy" && "animate-spin")} /> {scanLabel}
        </button>
        <Link
          href="/settings"
          aria-current={isActive("/settings") ? "page" : undefined}
          className={cn(
            "flex items-center gap-2 border-t border-border px-4 py-2.5 text-xs uppercase tracking-wider transition-colors",
            isActive("/settings") ? "text-fg-strong" : "text-muted hover:text-fg",
          )}
        >
          <Settings size={13} /> {t.nav.settings}
        </Link>
        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3 text-[10px]">
          <Clock />
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
