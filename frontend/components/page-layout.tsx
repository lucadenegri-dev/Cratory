import type { ReactNode } from "react";

export function PageLayout({
  title,
  meta,
  marginalia,
  marginaliaTitle,
  children,
}: {
  title?: string;
  meta?: ReactNode;
  marginalia?: ReactNode;
  marginaliaTitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={marginalia ? "lg:grid lg:grid-cols-[1fr_240px]" : ""}>
      <section className="min-w-0 px-5 py-5 lg:px-6 lg:py-6">
        {title && (
          <header className="mb-5 flex items-baseline gap-3 border-b border-border pb-3">
            <h1 className="text-sm font-semibold uppercase tracking-[0.12em] text-fg-strong">{title}</h1>
            {meta != null && <span className="tnum text-xs text-muted">{meta}</span>}
          </header>
        )}
        {children}
      </section>
      {marginalia && (
        <aside className="border-t border-border px-5 py-5 lg:border-l lg:border-t-0 lg:py-6">
          {marginaliaTitle && (
            <div className="mb-3 text-[10px] uppercase tracking-wider text-muted">{marginaliaTitle}</div>
          )}
          {marginalia}
        </aside>
      )}
    </div>
  );
}
