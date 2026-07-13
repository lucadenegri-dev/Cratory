import Link from "next/link";
import { cn } from "@/lib/cn";
import { BTN_VARIANT, BTN_SIZE, type Variant, type Size } from "@/components/ui";
import type { ComponentProps } from "react";

/* Link con l'aspetto esatto del Button di components/ui.tsx.
   Evita il nesting non valido <Link><Button> (interattivo dentro interattivo):
   la navigazione resta un <a>, lo stile resta quello dei bottoni.
   Variante/dimensione riusano BTN_VARIANT / BTN_SIZE di ui.tsx: qui resta solo
   il BTN_BASE proprio (senza display/disabled, vedi sotto). */

// Come BTN_BASE di ui.tsx, senza la classe display: qui è una prop tipizzata
// `block` invece di una classe passata in className (ora che cn fa il merge
// via twMerge non è più un workaround, resta una scelta di API più esplicita)
// e senza gli stati disabled (un link non è disabilitabile).
const BTN_BASE =
  "items-center justify-center gap-2 font-medium uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg";

export function ButtonLink({
  variant = "primary", size = "md", block = false, className, children, ...props
}: ComponentProps<typeof Link> & { variant?: Variant; size?: Size; block?: boolean }) {
  return (
    <Link
      className={cn(block ? "flex" : "inline-flex", BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size], className)}
      {...props}
    >
      {children}
    </Link>
  );
}
