"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { fmtDate, type DownloadStatus, type PipelineStatus, type Track } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Badge, EqMeter } from "@/components/ui";

/** Le code si muovono? Decide se il polling della dashboard resta acceso. */
export function queuesActive(download: DownloadStatus | null, pipeline: PipelineStatus | null): boolean {
  return download?.status === "running" || pipeline?.download_active === true;
}

/* Riga da registro: numero progressivo in faint, contenuto a destra. La
   numerazione segue le sole righe visibili, non le fasi possibili. */
function Row({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3">
      <span className="tnum pt-0.5 text-[10px] text-faint">{String(n).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

type Props = {
  download: DownloadStatus | null;
  pending: Track[];
  inboxFiles: number | null;
  leads: Track[];
};

/** «Il banco»: il lavoro aperto sulla catena di acquisizione. Ogni riga compare
 *  solo se ha contenuto; il vuoto è dichiarato, mai riempito di segnaposto. */
export function OpenWork({ download, pending, inboxFiles, leads }: Props) {
  const t = useT();

  const running = download?.status === "running";
  const reviewCount = Math.max(pending.length, download?.needs_review ?? 0);
  const inbox = inboxFiles ?? 0;

  const rows: ReactNode[] = [];

  if (running && download) {
    const pct = download.total > 0 ? (download.processed / download.total) * 100 : null;
    rows.push(
      <Link key="dl" href="/wishlist" className="block transition-colors hover:bg-elevated">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[10px] uppercase tracking-wider text-fg-strong">{t.dashboard.owDownloading}</span>
          {download.current_label && <span className="truncate text-xs text-muted">{download.current_label}</span>}
        </div>
        <EqMeter value={pct} className="mt-2 h-4 w-full" />
      </Link>,
    );
  }

  if (reviewCount > 0) {
    rows.push(
      <Link key="review" href="/wishlist" className="block transition-colors hover:bg-elevated">
        <span className="text-sm text-fg-strong">{t.dashboard.owToReview(reviewCount)}</span>
        {pending.length > 0 && (
          <span className="ml-3 text-xs text-muted">
            {pending.slice(0, 3).map((p) => [p.artist, p.title].filter(Boolean).join(" — ")).join(" · ")}
          </span>
        )}
      </Link>,
    );
  }

  if (inbox > 0) {
    rows.push(
      <Link key="inbox" href="/organize/files" className="block transition-colors hover:bg-elevated">
        <span className="text-sm text-fg-strong">{t.dashboard.owInbox(inbox)}</span>
      </Link>,
    );
  }

  if (leads.length > 0) {
    rows.push(
      <div key="leads">
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.dashboard.owLeads}</span>
          <Link href="/library" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">→</Link>
        </div>
        <ul>
          {leads.map((l) => (
            <li key={l.id}>
              <Link href={`/tracks/${l.id}`} className="flex items-baseline gap-3 py-1 transition-colors hover:bg-elevated">
                <span className="min-w-0 truncate text-sm text-fg">
                  {[l.artist, l.title].filter(Boolean).join(" — ")}
                </span>
                <Badge>{l.platform ?? l.source_type}</Badge>
                {l.added_at && <span className="tnum ml-auto shrink-0 text-[10px] text-faint">{fmtDate(l.added_at)}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </div>,
    );
  }

  return (
    <section className="mt-6">
      <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{t.dashboard.openWork}</h2>
      {rows.length === 0 ? (
        <div className="border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
          {t.dashboard.owNone}
        </div>
      ) : (
        <div className="divide-y divide-border border-y border-border">
          {rows.map((r, i) => (
            <Row key={i} n={i + 1}>{r}</Row>
          ))}
        </div>
      )}
    </section>
  );
}
