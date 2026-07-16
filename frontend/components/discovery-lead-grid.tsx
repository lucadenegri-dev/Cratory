"use client";

import { useState } from "react";
import { Disc3, Play } from "lucide-react";
import { type DiscoveryDigResponse, type DiscoveryLead, type Reason } from "@/lib/api";
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

export const FORMAT_VALUES = ["LP", "EP", "12\"", "Album", "Single"] as const;
export type SortMode = "score" | "recent";

// La lente sui risultati gia' scaricati: formato -> ordinamento -> taglio.
// Il taglio viene DOPO il formato, cosi' "40 di 240" conta cio' che il filtro ha
// lasciato e i numeri non mentono. Pura e testabile: page.tsx la usa per la lista
// E per il conteggio, quindi i due non possono divergere.
export function applyLens(
  leads: DiscoveryLead[],
  opts: { format: string | null; sort: SortMode; show: number | "all" },
): { visible: DiscoveryLead[]; total: number } {
  const base = opts.format === null ? leads : leads.filter((l) => l.format_badge === opts.format);
  const sorted = opts.sort === "score" ? base : [...base].sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  return { visible: opts.show === "all" ? sorted : sorted.slice(0, opts.show), total: base.length };
}

export function DiscoveryLeadGrid({ dig, leads }: {
  dig: DiscoveryDigResponse;
  // La lista GIA' passata dalla lente (formato+ordinamento+taglio, in page.tsx):
  // la griglia rende cio' che riceve, non filtra — cosi' il conteggio "N di M"
  // nella riga della risposta e le card mostrate escono dallo stesso calcolo.
  leads: DiscoveryLead[];
}) {
  const t = useT();
  const [openLead, setOpenLead] = useState<DiscoveryLead | null>(null);

  // Zero lead ha due cause diverse, e dirle uguali mente. Se la pila non esiste
  // (`pile_pages === 0`) il seme e' sconosciuto a Discogs: la libreria non c'entra e
  // "vai piu' a fondo" e' un consiglio che non puo' funzionare, perche' non c'e' fondo.
  // Se invece la pila c'e', i dischi sono stati filtrati (li possiedi gia') e scavare
  // piu' a fondo e' esattamente la mossa giusta.
  if (dig.pile_pages === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title={t.discovery.deadSeedTitle}>
        {t.discovery.deadSeedBody(dig.value)}
      </EmptyState>
    );
  }

  if (dig.leads.length === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
        {t.discovery.nothingToDigBody(dig.value, dig.seed_type === "label" ? t.discovery.seedTypeValue : t.discovery.seedTypeStyle)}
      </EmptyState>
    );
  }

  return (
    <div>
      {leads.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
          {leads.map((l, i) => (
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
                addInput: {
                  artist: lead.artist,
                  title: lead.title,
                  album_art_url: lead.thumb_url,
                  url: lead.discogs_url,
                },
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
