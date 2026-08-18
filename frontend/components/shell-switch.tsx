"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { EditorialShell } from "./editorial-shell";

/* Il wizard è a schermo intero: niente indice laterale. I children restano
   renderizzati dal server — qui si sceglie soltanto la cornice. */
export function ShellSwitch({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/setup") return <main className="min-h-screen">{children}</main>;
  return <EditorialShell>{children}</EditorialShell>;
}
