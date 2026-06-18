"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Library, ListPlus, ListMusic, Settings, Compass, Radar } from "lucide-react";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/playlists", label: "Playlist", icon: ListPlus },
  { href: "/library", label: "Libreria", icon: Library },
  { href: "/discovery", label: "Discovery", icon: Compass },
  { href: "/shazam", label: "Shazam", icon: Radar },
  { href: "/sets", label: "Set", icon: ListMusic },
  { href: "/settings", label: "Impostazioni", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <aside className="flex w-16 shrink-0 flex-col border-r border-border bg-surface lg:w-60">
      {/* Header logo */}
      <div className="flex items-center justify-center px-3 py-4 lg:justify-start lg:px-5">
        <img src="/logo.png" alt="SetArc" className="h-10 w-10 shrink-0 rounded-xl object-cover lg:h-16 lg:w-16" />
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2 lg:px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center justify-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors lg:justify-start",
                active ? "bg-elevated font-medium text-fg" : "text-muted hover:bg-elevated/60 hover:text-fg",
              )}
            >
              <Icon size={18} className={cn("shrink-0", active && "text-primary")} />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
