"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Sparkles, ListMusic, Clock, ChevronRight } from "lucide-react";
import { apiGet, fmtDuration, type SetlistSummary } from "@/lib/api";
import { Card, Badge, Alert, EmptyState, Button } from "@/components/ui";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

export default function SetsPage() {
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Set</h1>
          <p className="mt-1 text-sm text-muted">{sets?.length ?? 0} salvati</p>
        </div>
        <Link href="/set-builder"><Button size="sm"><Sparkles size={15} /> Nuovo set</Button></Link>
      </header>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {sets && sets.length === 0 && (
        <EmptyState icon={<ListMusic size={28} />} title="Nessun set salvato">
          Genera la tua prima scaletta nel <Link href="/set-builder" className="text-info hover:underline">Set Builder</Link>.
        </EmptyState>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sets?.map((s) => (
          <Link key={s.id} href={`/sets/${s.id}`} className="group">
            <Card className="h-full p-4 transition-colors hover:border-border-strong">
              <div className="mb-3 flex items-start justify-between gap-2">
                <h3 className="truncate font-medium leading-snug group-hover:text-primary">{s.name}</h3>
                <Badge tone={s.generated_by === "ai" ? "primary" : "neutral"}>
                  {s.generated_by === "ai" ? <><Sparkles size={11} /> AI</> : "algo"}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1"><ListMusic size={13} /> {s.track_count} tracce</span>
                {s.total_duration_seconds > 0 && (
                  <span className="tnum inline-flex items-center gap-1"><Clock size={13} /> {fmtDuration(s.total_duration_seconds)}</span>
                )}
                {s.strategy && <Badge>{s.strategy}</Badge>}
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-faint">
                <span>{fmtDate(s.created_at)}</span>
                <ChevronRight size={15} className="transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
