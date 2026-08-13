"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { type PipelineStatus } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Card } from "@/components/ui";

/* Una fase della striscia: numero vivo + etichetta, "accesa" (pallino) se c'è
   lavoro pendente. Ogni fase naviga alla sua pagina; Organizza porta dritta a
   FILES (era un pannello inline quando Organize era un'app separata). */
type StageDef = {
  key: string;
  label: string;
  value: string;
  sub: string;
  hot: boolean;
  href: string;
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
      href: "/organize/files",
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

  return (
    <Card>
      <div className="flex items-stretch overflow-x-auto">
        {stages.map((s, i) => (
          <div key={s.key} className="flex flex-1 items-center">
            {i > 0 && <ChevronRight size={14} className="shrink-0 text-faint" aria-hidden />}
            <Link href={s.href} className="flex-1 transition-colors hover:bg-elevated">
              <StageCell s={s} />
            </Link>
          </div>
        ))}
      </div>
    </Card>
  );
}
