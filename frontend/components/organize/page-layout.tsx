"use client";

import type { ReactNode } from "react";
import { useT } from "@/lib/i18n";

export function PageLayout({
  title, meta, marginalia, marginaliaTitle, guide, children,
}: {
  title?: string;
  meta?: ReactNode;
  marginalia?: ReactNode;
  marginaliaTitle?: string;
  guide?: ReactNode;
  children: ReactNode;
}) {
  const t = useT();
  const hasAside = marginalia != null || guide != null;
  return (
    <div className={hasAside ? "lg:grid lg:grid-cols-[1fr_240px]" : ""}>
      <section className="min-w-0 px-5 py-5 lg:px-6 lg:py-6">
        {title && (
          <header className="mb-5 flex items-baseline gap-3 border-b border-border pb-3">
            <h1 className="text-sm font-semibold uppercase tracking-[0.12em] text-fg-strong">{title}</h1>
            {meta != null && <span className="tnum text-xs text-muted">{meta}</span>}
          </header>
        )}
        {children}
      </section>
      {hasAside && (
        <aside className="border-t border-border px-5 py-5 lg:border-l lg:border-t-0 lg:py-6">
          {marginalia && (
            <>
              {marginaliaTitle && (
                <div className="mb-3 text-[10px] uppercase tracking-wider text-muted">{marginaliaTitle}</div>
              )}
              {marginalia}
            </>
          )}
          {guide && (
            <div className={marginalia ? "mt-6 border-t border-border pt-4" : ""}>
              <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.organize.common.guide}</div>
              <div className="space-y-1.5 text-[11px] leading-relaxed text-faint">{guide}</div>
            </div>
          )}
        </aside>
      )}
    </div>
  );
}
