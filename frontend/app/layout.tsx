import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "DJ Assistant",
  description: "AI DJ Set Builder & Library Expansion Assistant",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/library", label: "Library" },
  { href: "/set-builder", label: "Set Builder" },
  { href: "/transitions", label: "Transition Finder" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className="h-full antialiased">
      <body className="min-h-full bg-zinc-950 text-zinc-100">
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r border-zinc-800 p-4">
            <h1 className="mb-6 text-lg font-bold tracking-tight">
              🎧 DJ Assistant
            </h1>
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <p className="mt-8 text-xs text-zinc-600">MVP 1 — motore deterministico</p>
          </aside>
          <main className="flex-1 overflow-x-auto p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
