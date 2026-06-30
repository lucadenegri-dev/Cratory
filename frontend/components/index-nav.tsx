"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings } from "lucide-react";
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
  { href: "/downloads", label: "Download" },
];

export function IndexNav() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

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

      <div className="hidden lg:block">
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
