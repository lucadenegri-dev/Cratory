"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { libraryStats, type LibraryStats } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useJobs } from "./jobs-provider";
import { Clock } from "./clock";
import { ThemeToggle } from "./theme-toggle";
import { useT } from "@/lib/i18n";

const NAV = [
  { href: "/files", label: "Files" },
  { href: "/issues", label: "Issues" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/plan", label: "Plan" },
  { href: "/history", label: "History" },
] as const;

function sumIssues(s: LibraryStats | null): number {
  if (!s) return 0;
  return Object.values(s.issues_by_severity).reduce((a, b) => a + b, 0);
}

export function IndexNav() {
  const pathname = usePathname();
  const t = useT();
  const { scan } = useJobs();
  const [stats, setStats] = useState<LibraryStats | null>(null);

  const load = useCallback(() => {
    libraryStats().then(setStats).catch(() => setStats(null));
  }, []);

  // ricarica i conteggi all'avvio, al cambio pagina, e quando uno scan finisce
  useEffect(() => { load(); }, [pathname, load]);
  useEffect(() => {
    if (scan.status === "done") load();
  }, [scan.status, load]);

  const counts: Record<string, string> = {
    "/files": stats ? String(stats.files_total) : "—",
    "/issues": stats ? String(sumIssues(stats)) : "—",
    "/duplicates": stats ? String(stats.dup_groups) : "—",
    "/plan": "—",
    "/history": "—",
  };

  const isActive = (href: string) => pathname.startsWith(href);

  return (
    <nav className="flex h-full flex-col">
      <div className="px-4 py-4">
        <Link href="/files" className="block text-sm font-semibold tracking-[0.12em] text-fg-strong">
          SORTORY
        </Link>
        <p className="mt-1 text-[9px] uppercase tracking-wider text-faint">{t.nav.tagline}</p>
      </div>

      <ul className="flex gap-4 overflow-x-auto px-2 pb-3 lg:flex-1 lg:flex-col lg:gap-px lg:overflow-visible lg:pb-0">
        {NAV.map(({ href, label }) => {
          const active = isActive(href);
          return (
            <li key={href} className="shrink-0">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-between gap-2 whitespace-nowrap px-2 py-1.5 text-xs uppercase tracking-wider transition-colors",
                  active
                    ? "border-l-2 border-danger bg-surface-2 text-fg-strong"
                    : "border-l-2 border-transparent text-muted hover:text-fg",
                )}
              >
                <span>{label}</span>
                <span className={cn("tnum text-[10px]", active ? "text-fg" : "text-faint")}>
                  {counts[href]}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      {/* Settings in fondo (come Cratory): barra di separazione sopra + icona rotellina */}
      <div className="hidden flex-col border-t border-border lg:flex">
        <Link
          href="/settings"
          aria-current={isActive("/settings") ? "page" : undefined}
          className={cn(
            "flex items-center gap-1.5 px-2 py-1.5 text-xs uppercase tracking-wider transition-colors",
            isActive("/settings")
              ? "border-l-2 border-danger bg-surface-2 text-fg-strong"
              : "border-l-2 border-transparent text-muted hover:text-fg",
          )}
        >
          <span aria-hidden className="text-sm leading-none">⚙</span>
          Settings
        </Link>
        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3 text-[10px]">
          <Clock />
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
