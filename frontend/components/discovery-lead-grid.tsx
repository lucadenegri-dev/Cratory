"use client";

import { useMemo, useState } from "react";
import { Disc3, Play } from "lucide-react";
import { type DiscoveryDigResponse, type DiscoveryLead, type Reason } from "@/lib/api";
import { cn } from "@/lib/cn";
import { EmptyState } from "@/components/ui";
import { DiscoveryTracklistPanel } from "@/components/discovery-tracklist-panel";
import { useT, type Dictionary } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

function reasonLabel(r: Reason, t: Dictionary): string {
  switch (r.code) {
    case "rare_wanted":
      return t.discovery.reasonRareWanted(r.data.have, r.data.want);
    case "deep_cut":
      return t.discovery.reasonDeepCut;
    case "label_followed":
      return t.discovery.reasonLabelFollowed(r.data.label);
    case "artist_collected":
      return t.discovery.reasonArtistCollected;
    case "style_match":
      return t.discovery.reasonStyleMatch;
    case "recent":
      return t.discovery.reasonRecent(r.data.year);
    default:
      return r.code;
  }
}

const FORMAT_VALUES = ["LP", "EP", "12\"", "Album", "Single"] as const;
type FormatFilter = (typeof FORMAT_VALUES)[number] | null;
type SortMode = "score" | "recent";

export function DiscoveryLeadGrid({ dig }: { dig: DiscoveryDigResponse }) {
  const t = useT();
  const [format, setFormat] = useState<FormatFilter>(null);
  const [sort, setSort] = useState<SortMode>("score");
  const [openLead, setOpenLead] = useState<DiscoveryLead | null>(null);

  const formatOptions: [string, FormatFilter][] = [
    [t.discovery.formatAllOption, null],
    ...FORMAT_VALUES.map((f): [string, FormatFilter] => [f, f]),
  ];
  const SORT_OPTIONS: [SortMode, string][] = [["score", t.discovery.sortScore], ["recent", t.discovery.sortRecent]];

  const filtered = useMemo(() => {
    const base = format === null ? dig.leads : dig.leads.filter((l) => l.format_badge === format);
    if (sort === "score") return base;
    return [...base].sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  }, [dig.leads, format, sort]);

  if (dig.leads.length === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
        {t.discovery.nothingToDigBody(dig.value, dig.seed_type === "label" ? t.discovery.seedTypeValue : t.discovery.seedTypeStyle)}
      </EmptyState>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {formatOptions.map(([label, f]) => (
            <button
              key={f ?? "all"}
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
              {label}
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
        <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>
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
  const t = useT();
  const player = usePlayer();
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="group relative flex cursor-pointer flex-col gap-1.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-fg"
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
          <span className="absolute right-1 top-1 border border-border-strong bg-bg px-1 text-[9px] uppercase tracking-wide text-muted">
            {lead.format_badge}
          </span>
        )}
        <button
          type="button"
          aria-label={t.discovery.playPreview}
          className="absolute left-1 top-1 rounded-full bg-black/60 p-1.5 text-white opacity-0 transition group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            player.play({
              kind: "discovery-preview",
              item: {
                key: `r:${lead.discogs_id ?? "x"}`,
                artist: lead.artist,
                title: lead.title,
                discogsId: lead.discogs_id,
                level: "release",
                label: lead.title,
              },
            });
          }}
        >
          <Play size={14} />
        </button>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 translate-y-full bg-bg/95 px-1.5 py-1 text-[10px] leading-tight text-muted opacity-0 transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
          {lead.label && <div className="truncate">{lead.label}</div>}
          {lead.year != null && <div>{lead.year}</div>}
          {lead.reasons[0] && <div className="truncate text-faint">{reasonLabel(lead.reasons[0], t)}</div>}
        </div>
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-fg">{lead.title}</div>
        <div className="truncate text-[11px] text-faint">{lead.artist}</div>
      </div>
    </div>
  );
}
