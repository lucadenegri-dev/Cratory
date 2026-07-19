"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import { type PipelineStatus } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Card } from "@/components/ui";

/* Una fase della striscia: numero vivo + etichetta, "accesa" (pallino) se c'è
   lavoro pendente. Fasi con href navigano (Analizza -> /analysis); Organizza
   apre un pannello inline (link a Sortory). */
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
      <span className="text-[10px] leading-tight text-faint">{s.sub}</span>
    </div>
  );
}

export function PipelineStrip({ p }: { p: PipelineStatus }) {
  const t = useT();
  const [organizeOpen, setOrganizeOpen] = useState(false);

  const stages: StageDef[] = [
    {
      key: "scopri", label: t.dashboard.stageDiscover, value: String(p.playlists),
      sub: t.dashboard.stageDiscoverSub, hot: p.total_tracks === 0, href: "/playlists",
    },
    {
      key: "acquisisci", label: t.dashboard.stageAcquire, value: String(p.wishlist),
      sub: t.dashboard.stageAcquireSub(p.download_active, p.download_pending),
      hot: p.wishlist > 0 || p.download_active, href: "/wishlist",
    },
    {
      key: "organizza", label: t.dashboard.stageOrganize,
      value: p.inbox_files === null ? "—" : String(p.inbox_files),
      sub: t.dashboard.stageOrganizeSub, hot: (p.inbox_files ?? 0) > 0,
    },
    {
      key: "analizza", label: t.dashboard.stageAnalyze, value: String(p.analyze_pending),
      sub: t.dashboard.stageAnalyzeSub, hot: p.analyze_pending > 0, href: "/analysis",
    },
    {
      key: "suona", label: t.dashboard.stagePlay, value: String(p.ready_for_set),
      sub: t.dashboard.stagePlaySub, hot: false, href: "/set-builder",
    },
  ];

  const onStageClick = (key: string) => {
    if (key === "organizza") setOrganizeOpen((v) => !v);
  };

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
                onClick={() => onStageClick(s.key)}
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
              ? t.dashboard.inboxNotConfigured
              : t.dashboard.inboxWaiting(p.inbox_files)}
          </span>
          {p.organizer_url && (
            <a
              href={p.organizer_url} target="_blank" rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 text-fg-strong hover:underline"
            >
              {t.dashboard.openSortory} <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
    </Card>
  );
}
