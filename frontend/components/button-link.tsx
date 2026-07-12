import Link from "next/link";
import { cn } from "@/lib/cn";
import type { ComponentProps } from "react";

/* Link con l'aspetto esatto del Button di components/ui.tsx.
   Evita il nesting non valido <Link><Button> (interattivo dentro interattivo):
   la navigazione resta un <a>, lo stile resta quello dei bottoni.
   Le classi sotto replicano BTN_BASE / BTN_VARIANT / BTN_SIZE di ui.tsx
   (che non le esporta): se cambiano lì, vanno allineate anche qui. */

type Variant = "primary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md";

// Come BTN_BASE di ui.tsx, senza la classe display (gestita via prop `block`)
// e senza gli stati disabled (un link non è disabilitabile).
const BTN_BASE =
  "items-center justify-center gap-2 font-medium uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg";
const BTN_VARIANT: Record<Variant, string> = {
  primary: "bg-fg-strong text-bg hover:bg-fg",
  outline: "border border-border-strong bg-transparent text-fg hover:bg-elevated",
  ghost: "bg-transparent text-muted hover:bg-elevated hover:text-fg",
  danger: "border border-danger bg-transparent text-danger hover:bg-danger hover:text-bg",
};
const BTN_SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-xs",
};

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
