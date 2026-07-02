"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import { fmtDate, startLibraryIndex, type PipelineStatus } from "@/lib/api";
import { Card } from "@/components/ui";

/* Una fase della striscia: numero vivo + etichetta, "accesa" (pallino) se c'è
   lavoro pendente. Fasi con href navigano; Organizza apre il pannello cross-app;
   Indicizza lancia la scansione. */
type StageDef = {
  key: string;
  label: string;
  value: string;
  sub: string;
  hot: boolean;
  href?: string;
};

function StageCell({ s }: { s: StageDef }) {
  return (
    <div className="flex min-w-[8.5rem] flex-1 flex-col gap-0.5 px-4 py-3 text-left">
      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted">
        {s.label}
        {s.hot && <span className="h-1.5 w-1.5 rounded-full bg-fg-strong" aria-hidden />}
      </span>
      <span className={cn("tnum text-lg font-semibold", s.hot ? "text-fg-strong" : "text-fg")}>{s.value}</span>
      <span className="whitespace-nowrap text-[10px] text-faint">{s.sub}</span>
    </div>
  );
}

export function PipelineStrip({ p, onRefresh }: { p: PipelineStatus; onRefresh: () => void }) {
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [scanStarted, setScanStarted] = useState(false);

  const startScan = async () => {
    try {
      await startLibraryIndex();
      setScanStarted(true);
      onRefresh();
    } catch {
      /* 409 = LIBRARY_ROOT mancante o job già in corso: la striscia resta com'è */
    }
  };

  const diskConfigured = p.files_on_disk !== null;
  const stages: StageDef[] = [
    {
      key: "scopri", label: "Scopri", value: String(p.playlists),
      sub: "playlist importate", hot: p.total_tracks === 0, href: "/playlists",
    },
    {
      key: "arricchisci", label: "Arricchisci", value: String(p.missing_key),
      sub: "tracce senza key", hot: p.missing_key > 0, href: "/library",
    },
    {
      key: "acquisisci", label: "Acquisisci", value: String(p.wishlist),
      sub: p.download_active ? `download attivi · ${p.download_pending} in coda` : "in wishlist",
      hot: p.wishlist > 0 || p.download_active, href: "/downloads",
    },
    {
      key: "organizza", label: "Organizza ⤴",
      value: p.inbox_files === null ? "—" : String(p.inbox_files),
      sub: "inbox · DJPlayer → DjOrganizer", hot: (p.inbox_files ?? 0) > 0,
    },
    {
      key: "indicizza", label: "Indicizza",
      value: scanStarted ? "…" : p.index_mismatch ? "≠" : "ok",
      sub: scanStarted
        ? "scansione avviata"
        : p.last_index_at
          ? `ultima: ${fmtDate(p.last_index_at)} · clic per scansionare`
          : "mai eseguita · clic per scansionare",
      hot: !scanStarted && diskConfigured && (p.index_mismatch === true || !p.last_index_at),
    },
    {
      key: "suona", label: "Suona", value: String(p.ready_for_set),
      sub: "pronte per un set", hot: false, href: "/set-builder",
    },
  ];

  return (
    <Card>
      <div className="flex items-stretch overflow-x-auto">
        {stages.map((s, i) => (
          <div key={s.key} className="flex flex-1 items-center">
            {i > 0 && <ChevronRight size={14} className="shrink-0 text-faint" aria-hidden />}
            {s.href ? (
              <Link href={s.href} className="flex-1 transition-colors hover:bg-elevated">
                <StageCell s={s} />
              </Link>
            ) : (
              <button
                type="button"
                onClick={s.key === "organizza" ? () => setOrganizeOpen((v) => !v) : startScan}
                className="flex-1 transition-colors hover:bg-elevated"
              >
                <StageCell s={s} />
              </button>
            )}
          </div>
        ))}
      </div>
      {organizeOpen && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-xs text-muted">
          <span>
            {p.inbox_files === null
              ? "Inbox non configurata: imposta SLSKD_DOWNLOAD_DIR nel .env del backend."
              : `${p.inbox_files} file audio in inbox aspettano il triage (DJPlayer) e l'organizzazione (DjOrganizer); poi torna qui e indicizza.`}
          </span>
          {p.organizer_url && (
            <a
              href={p.organizer_url} target="_blank" rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 text-fg-strong hover:underline"
            >
              Apri DjOrganizer <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
    </Card>
  );
}
