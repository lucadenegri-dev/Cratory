"use client";

import { useMemo, useState } from "react";
import { Disc3 } from "lucide-react";
import { type DiscoveryDigResponse, type DiscoveryLead, type Reason } from "@/lib/api";
import { cn } from "@/lib/cn";
import { EmptyState } from "@/components/ui";
import { DiscoveryTracklistPanel } from "@/components/discovery-tracklist-panel";

function reasonLabel(r: Reason): string {
  switch (r.code) {
    case "rare_wanted":
      return `raro & richiesto ${r.data.have}/${r.data.want}`;
    case "deep_cut":
      return "deep cut";
    case "label_followed":
      return `etichetta che segui${r.data.label ? ` · ${r.data.label}` : ""}`;
    case "artist_collected":
      return "artista che collezioni";
    case "style_match":
      return "stile che ascolti";
    case "recent":
      return `recente${r.data.year ? ` · ${r.data.year}` : ""}`;
    default:
      return r.code;
  }
}

const FORMAT_FILTERS = ["Tutti", "LP", "EP", "12\"", "Album", "Single"] as const;
type FormatFilter = (typeof FORMAT_FILTERS)[number];
type SortMode = "score" | "recent";
const SORT_OPTIONS: [SortMode, string][] = [["score", "Punteggio"], ["recent", "Più recenti"]];

export function DiscoveryLeadGrid({ dig }: { dig: DiscoveryDigResponse }) {
  const [format, setFormat] = useState<FormatFilter>("Tutti");
  const [sort, setSort] = useState<SortMode>("score");
  const [openLead, setOpenLead] = useState<DiscoveryLead | null>(null);

  const filtered = useMemo(() => {
    const base = format === "Tutti" ? dig.leads : dig.leads.filter((l) => l.format_badge === format);
    if (sort === "score") return base;
    return [...base].sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  }, [dig.leads, format, sort]);

  if (dig.leads.length === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title="Niente da scavare">
        Nessun brano nuovo per “{dig.value}”. Prova un altro {dig.seed_type === "label" ? "valore" : "stile"} o alza l’audacia.
      </EmptyState>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {FORMAT_FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFormat(f)}
              aria-pressed={format === f}
              className={cn(
                "rounded-none border px-2.5 py-1 text-xs transition-colors",
                format === f
                  ? "border-border-strong bg-elevated text-fg"
                  : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
              )}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
          {SORT_OPTIONS.map(([s, label]) => (
            <button
              key={s}
              type="button"
              onClick={() => setSort(s)}
              aria-pressed={sort === s}
              className={cn(
                "rounded-none px-2.5 py-1 text-xs font-medium transition-colors",
                sort === s ? "bg-elevated text-fg" : "text-muted hover:text-fg",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">Nessun disco con questo formato.</p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
          {filtered.map((l, i) => (
            <LeadCell key={`${l.discogs_id ?? l.artist}-${l.title}-${i}`} lead={l} onOpen={() => setOpenLead(l)} />
          ))}
        </div>
      )}

      <DiscoveryTracklistPanel lead={openLead} onClose={() => setOpenLead(null)} />
    </div>
  );
}

function LeadCell({ lead, onOpen }: { lead: DiscoveryLead; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative flex flex-col gap-1.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-fg"
    >
      <div className="relative aspect-square w-full overflow-hidden border border-border bg-elevated">
        {lead.thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={lead.thumb_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center text-faint">
            <Disc3 size={22} />
          </div>
        )}
        {lead.format_badge && (
          <span className="absolute left-1 top-1 border border-border-strong bg-bg px-1 text-[9px] uppercase tracking-wide text-muted">
            {lead.format_badge}
          </span>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 translate-y-full bg-bg/95 px-1.5 py-1 text-[10px] leading-tight text-muted opacity-0 transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
          {lead.label && <div className="truncate">{lead.label}</div>}
          {lead.year != null && <div>{lead.year}</div>}
          {lead.reasons[0] && <div className="truncate text-faint">{reasonLabel(lead.reasons[0])}</div>}
        </div>
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-fg">{lead.title}</div>
        <div className="truncate text-[11px] text-faint">{lead.artist}</div>
      </div>
    </button>
  );
}
