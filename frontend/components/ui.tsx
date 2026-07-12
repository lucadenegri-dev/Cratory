"use client";

import { ChevronDown, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import type { ButtonHTMLAttributes, CSSProperties, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

/* ---------------------------------------------------------------- Card */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("border border-border bg-surface", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h3 className="font-semibold uppercase tracking-wider text-fg-strong">{title}</h3>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/* -------------------------------------------------------------- Button */

type Variant = "primary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md";

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 font-medium uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg";
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

export function Button({
  variant = "primary", size = "md", className, children, ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button className={cn(BTN_BASE, BTN_VARIANT[variant], BTN_SIZE[size], className)} {...props}>
      {children}
    </button>
  );
}

/* --------------------------------------------------------------- Inputs */

const FIELD =
  "w-full border border-border bg-bg px-3 text-sm text-fg placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-1 focus:ring-fg";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(FIELD, "py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative w-full">
      <select className={cn(FIELD, "h-10 cursor-pointer appearance-none bg-bg pr-8", className)} {...props}>
        {children}
      </select>
      <ChevronDown
        size={15}
        aria-hidden
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-faint"
      />
    </div>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Checkbox({ label, checked, onChange, disabled }: {
  label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean;
}) {
  return (
    <label className={cn("flex items-center gap-2 text-sm", disabled ? "text-faint" : "cursor-pointer text-fg")}>
      <input
        type="checkbox" checked={checked} disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-[var(--color-fg)]"
      />
      {label}
    </label>
  );
}

/* ---------------------------------------------------------------- Badge */

type Tone = "neutral" | "primary" | "info" | "warning" | "danger" | "success";
const BADGE_TONE: Record<Tone, string> = {
  neutral: "bg-elevated text-muted",
  primary: "bg-elevated text-fg",
  info: "bg-elevated text-muted",
  warning: "bg-elevated text-muted",
  danger: "border border-danger text-danger",
  success: "bg-elevated text-muted",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider", BADGE_TONE[tone], className)}>
      {children}
    </span>
  );
}

/* Loader inline: equalizzatore a colonne con tacca di picco calda. */
export function Equalizer({ className }: { className?: string }) {
  const t = useT();
  return (
    <span role="status" aria-label={t.common.loading} className={cn("eq", className ?? "h-4 w-4")}>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l1" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l2" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l3" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l5" /></span>
    </span>
  );
}

/* Alias di compatibilita': i consumer che importano Spinner restano invariati. */
export const Spinner = Equalizer;


/** Trattamento standard del caricamento pagina: Equalizer + testo muted. */
export function Loading({ label }: { label?: string }) {
  const t = useT();
  return (
    <p className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <Equalizer /> {label ?? t.common.loading}
    </p>
  );
}

/* Meter "terminale": blocchi █ in danger su dither ░ chiaro. value numerico ->
   riempimento a blocchi con cursore lampeggiante nello slot successivo;
   value null -> indeterminato con treno di blocchi che avanza a scatti.
   calm: rapporti statici (es. copertura) -> niente cursore, tutto fermo. */
export function EqMeter({ value, className, calm = false }: { value: number | null; className?: string; calm?: boolean }) {
  const t = useT();
  const indeterminate = value == null;
  const v = indeterminate ? 0 : Math.min(100, Math.max(0, value));
  const w = { "--w": `${v}%` } as CSSProperties;
  return (
    <div
      className={cn("eqm", calm && "eqm-calm", className ?? "h-6 w-full")}
      role={indeterminate ? "status" : "progressbar"}
      aria-label={indeterminate ? t.common.inProgress : undefined}
      aria-valuenow={indeterminate ? undefined : Math.round(v)}
      aria-valuemin={indeterminate ? undefined : 0}
      aria-valuemax={indeterminate ? undefined : 100}
    >
      <span className="eqm-rest" />
      {indeterminate ? (
        <span className="eqm-scan" />
      ) : (
        <>
          <span className="eqm-fill" style={w} />
          {!calm && v < 100 && <span className="eqm-cursor" style={w} />}
        </>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- Empty / msg */

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center border border-dashed border-border px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <p className="font-medium text-fg-strong">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- Modal */

export function Modal({ open, onClose, title, children, footer, size = "md" }: {
  open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; footer?: ReactNode;
  size?: "md" | "lg";
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Focus del pannello SOLO all'apertura. Non dipende da onClose: le pagine
  // con poller (es. /downloads) passano una onClose inline che cambia identità
  // a ogni render; se il focus fosse qui insieme a onClose, ogni poll ruberebbe
  // il focus a un input mentre l'utente scrive (il campo sembra "non editabile").
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-black/70 p-4 pt-[10vh]"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        className={cn("w-full border border-border-strong bg-surface outline-none", size === "lg" ? "max-w-lg" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3.5">
            <h3 id="modal-title" className="font-semibold uppercase tracking-wider text-fg-strong">{title}</h3>
            <button onClick={onClose} className="text-faint transition-colors hover:text-fg"><X size={18} /></button>
          </div>
        )}
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "warning" | "info" | "success"; children: ReactNode }) {
  const isDanger = tone === "danger";
  return (
    <div className={cn(
      "border px-4 py-3 text-sm",
      isDanger ? "border-danger text-danger" : "border-border text-fg",
    )}>
      {children}
    </div>
  );
}
