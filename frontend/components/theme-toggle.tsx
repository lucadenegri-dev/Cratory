"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "paper";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("djorganizer-theme") as Theme | null) ?? "dark";
    const raf = requestAnimationFrame(() => setTheme(stored));
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "paper" : "dark";
    setTheme(next);
    localStorage.setItem("djorganizer-theme", next);
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
