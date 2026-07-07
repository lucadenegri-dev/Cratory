"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { RefreshCw, Settings } from "lucide-react";
import { cn } from "@/lib/cn";
import { startLibraryIndex } from "@/lib/api";
import { Clock } from "./clock";
import { ThemeToggle } from "./theme-toggle";

/* Il menu racconta la sequenza del flusso: Scopri → Colleziona → Suona. */
const NAV_GROUPS: { title: string | null; items: { href: string; label: string }[] }[] = [
  { title: null, items: [{ href: "/", label: "Dashboard" }] },
  {
    title: "Scopri",
    items: [
      { href: "/playlists", label: "Playlist" },
      { href: "/discovery", label: "Discovery" },
      { href: "/shazam", label: "Shazam" },
      { href: "/labels", label: "Etichette" },
    ],
  },
  {
    title: "Colleziona",
    items: [
      { href: "/library", label: "Libreria" },
      { href: "/downloads", label: "Download" },
    ],
  },
  {
    title: "Suona",
    items: [
      { href: "/set-builder", label: "Set Builder" },
      { href: "/sets", label: "Set" },
      { href: "/transitions", label: "Transizioni" },
    ],
  },
];

export function IndexNav() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

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
  const scanLabel = scan === "busy" ? "Avvio…" : scan === "done" ? "Avviata" : "Indicizza";

  return (
    <nav className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block">
        <Link href="/" className="block text-sm font-semibold tracking-[0.16em] text-fg-strong">CRATORY</Link>
        <p className="hidden text-[10px] uppercase tracking-wider text-muted lg:mt-1 lg:block">Workbench per DJ set</p>
        <div className="flex items-center gap-3 text-[10px] lg:hidden">
          <Link href="/settings" aria-label="Impostazioni" aria-current={isActive("/settings") ? "page" : undefined} className={cn("transition-colors hover:text-fg", isActive("/settings") ? "text-fg-strong" : "text-muted")}><Settings size={14} /></Link>
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
              <div className="hidden lg:mb-1 lg:mt-4 lg:block text-[9px] font-semibold uppercase tracking-[0.14em] text-faint">
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
                      "block whitespace-nowrap py-1 text-xs uppercase tracking-wider transition-colors",
                      isActive(href) ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg",
                    )}
                  >
                    {label}
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
          <Settings size={13} /> Impostazioni
        </Link>
        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3 text-[10px]">
          <Clock />
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
