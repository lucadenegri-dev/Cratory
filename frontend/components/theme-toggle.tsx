"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

type Theme = "dark" | "paper";

export function ThemeToggle() {
  const t = useT();
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("cratory-theme") as Theme | null) ?? "dark";
    const raf = requestAnimationFrame(() => setTheme(stored));
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "paper" : "dark";
    setTheme(next);
    localStorage.setItem("cratory-theme", next);
    if (next === "paper") {
      document.documentElement.setAttribute("data-theme", "paper");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  };

  return (
    <button
      onClick={toggle}
      aria-label={t.nav.toggleTheme}
      className="inline-flex items-center gap-1.5 uppercase tracking-wider text-muted transition-colors hover:text-fg"
    >
      <span aria-hidden>◑</span>
      {theme === "dark" ? "Paper" : "Dark"}
    </button>
  );
}
