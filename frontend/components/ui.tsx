"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

/* ---------------------------------------------------------------- Card */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-[var(--radius)] border border-border bg-surface", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h3 className="font-semibold tracking-tight">{title}</h3>
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
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50";
const BTN_VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:bg-primary-hover",
  outline: "border border-border-strong bg-transparent text-fg hover:bg-elevated",
  ghost: "bg-transparent text-muted hover:bg-elevated hover:text-fg",
  danger: "bg-danger/15 text-danger hover:bg-danger/25",
};
const BTN_SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
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
  "w-full rounded-lg border border-border bg-bg px-3 text-sm text-fg placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-primary/30";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(FIELD, "py-2 leading-relaxed", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(FIELD, "h-10 cursor-pointer appearance-none bg-bg pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
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
        className="h-4 w-4 accent-[var(--color-primary)]"
      />
      {label}
    </label>
  );
}

/* ---------------------------------------------------------------- Badge */

type Tone = "neutral" | "primary" | "info" | "warning" | "danger" | "success";
const BADGE_TONE: Record<Tone, string> = {
  neutral: "bg-elevated text-muted",
  primary: "bg-primary/15 text-primary",
  info: "bg-info/15 text-info",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
  success: "bg-success/15 text-success",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium", BADGE_TONE[tone], className)}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------- Progress bar */

export function Progress({ value }: { value: number | null }) {
  const indeterminate = value == null;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-elevated">
      <div
        className={cn("h-full rounded-full bg-primary transition-all", indeterminate && "w-1/3 animate-shimmer")}
        style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-block animate-spin rounded-full border-2 border-border-strong border-t-primary", className ?? "h-4 w-4")} />
  );
}

/* ----------------------------------------------------------- Empty / msg */

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius)] border border-dashed border-border px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <p className="font-medium text-fg">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- Modal */

export function Modal({ open, onClose, title, children, footer, size = "md" }: {
  open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; footer?: ReactNode;
  size?: "md" | "lg";
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[10vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={cn("w-full rounded-[var(--radius)] border border-border bg-surface shadow-2xl", size === "lg" ? "max-w-lg" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3.5">
            <h3 className="font-semibold tracking-tight">{title}</h3>
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
  const tones = {
    danger: "border-danger/30 bg-danger/10 text-danger",
    warning: "border-warning/30 bg-warning/10 text-warning",
    info: "border-info/30 bg-info/10 text-info",
    success: "border-success/30 bg-success/10 text-success",
  };
  return <div className={cn("rounded-lg border px-4 py-3 text-sm", tones[tone])}>{children}</div>;
}
