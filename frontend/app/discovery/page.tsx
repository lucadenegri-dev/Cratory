"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Disc3 } from "lucide-react";
import {
  discoveryDig,
  errText,
  getDiscoveryGenres,
  listImportedPlaylists,
  getLabels,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type Playlist,
  type LabelStats,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { DiscoveryLeadGrid, FORMAT_VALUES } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar, type SeedType } from "@/components/discovery-dig-bar";
import { useT } from "@/lib/i18n";

type SortMode = "score" | "recent";

function DiscoveryInner() {
  const t = useT();
  const jobs = useJobs();

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialSeed = (searchParams.get("seed") === "label" ? "label" : "genre") as SeedType;
  const initialValue = searchParams.get("value") ?? "";
  const initialDepthRaw = Number(searchParams.get("depth") ?? "0");
  const initialDepth = Number.isFinite(initialDepthRaw) ? Math.min(1, Math.max(0, initialDepthRaw)) : 0;
  const initialTaste = searchParams.get("taste");

  // riferimento di gusto (playlist) per il dig
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [labels, setLabels] = useState<LabelStats[] | null>(null);

  // scava (dig Discogs) — il soggetto (genere o etichetta) è un unico campo:
  // il seed_type è derivato da quale gruppo dell'autocomplete è stato scelto.
  const [seedType, setSeedType] = useState<SeedType>(initialSeed);
  const [subject, setSubject] = useState(initialValue);
  const [depth, setDepth] = useState(initialDepth);
  const [tasteRef, setTasteRef] = useState<number | null>(initialTaste ? Number(initialTaste) : null); // null = tutta la libreria
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

  // lenti sui risultati già ottenuti: fuori dall'URL, non rilanciano il dig
  const [format, setFormat] = useState<string | null>(null);
  const [sort, setSort] = useState<SortMode>("score");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listImportedPlaylists()
      .then(setPlaylists)
      .catch((e) => setError(errText(e)));
    getDiscoveryGenres()
      .then(setGenres)
      .catch(() => setGenres({ library: [], styles: [] }));
    getLabels()
      .then(setLabels)
      .catch(() => setLabels([]));
  }, []);

  const executeDig = useCallback(
    async (seed: SeedType, value: string, d: number, taste: number | null) => {
      setBusy(true);
      setError(null);
      setDig(null);
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `Discogs · ${value}` });
      try {
        setDig(await discoveryDig(seed, value, { depth: d, tastePlaylistId: taste }));
      } catch (e) {
        setError(errText(e));
      } finally {
        setBusy(false);
        jobs.endClientJob("dig");
      }
    },
    [jobs, t],
  );

  const paramsKey = searchParams.toString();
  useEffect(() => {
    const seed: SeedType = searchParams.get("seed") === "label" ? "label" : "genre";
    const value = searchParams.get("value") ?? "";
    if (!value) return; // pagina aperta senza un dig: mostra l'empty state, non eseguire
    const depthRaw = Number(searchParams.get("depth") ?? "0");
    const d = Number.isFinite(depthRaw) ? Math.min(1, Math.max(0, depthRaw)) : 0;
    const tasteRaw = Number(searchParams.get("taste"));
    const taste = Number.isFinite(tasteRaw) && tasteRaw > 0 ? tasteRaw : null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(seed, value, d, taste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const runDig = () => {
    const value = subject.trim();
    if (!value) return;
    const params = new URLSearchParams();
    params.set("seed", seedType);
    params.set("value", value);
    params.set("depth", String(depth));
    if (tasteRef != null) params.set("taste", String(tasteRef));
    // Params identici a quelli già nell'URL: la ricerca è deterministica, il
    // risultato sarebbe lo stesso. Non pushare, così non si accumula una voce
    // di cronologia duplicata (back richiederebbe due click).
    if (params.toString() === searchParams.toString()) return;
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const digReady = !!subject.trim();
  // Invalida a ogni cambio di seme (soggetto o tipo): senza questo controllo `pilePages`
  // resta legato all'ULTIMA risposta, non al soggetto corrente digitato — il controllo
  // di profondita' restava disabilitato (pila corta di prima) finche' non si rilanciava
  // il dig, contro la spec ("disabled fino al prossimo cambio di seme").
  const pilePages =
    dig && dig.seed_type === seedType && dig.value === subject.trim() ? dig.pile_pages : null;

  return (
    <PageLayout title="Discovery">
      <p className="mb-4 text-sm text-muted">{t.discovery.intro}</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <DiscoveryDigBar
        subject={subject}
        onSubjectChange={(value, seed) => {
          setSubject(value);
          setSeedType(seed);
        }}
        depth={depth}
        onDepthChange={setDepth}
        tasteRef={tasteRef}
        onTasteRefChange={setTasteRef}
        options={{
          genres: genres ?? { library: [], styles: [] },
          labels: labels?.map((l) => l.label) ?? [],
          playlists: playlists?.map((p) => ({ id: p.id, name: p.name })) ?? [],
        }}
        pilePages={pilePages}
        busy={busy}
        ready={digReady}
        onSubmit={runDig}
      />

      {dig && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border pb-3 text-xs">
          <span className="tnum text-muted">{t.discovery.leadCount(dig.leads.length)}</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.formatLabel}</span>
            <div className="flex flex-wrap gap-1.5">
              <Chip on={format === null} onClick={() => setFormat(null)}>{t.discovery.formatAll}</Chip>
              {FORMAT_VALUES.map((f) => (
                <Chip key={f} on={format === f} onClick={() => setFormat(f)}>{f}</Chip>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.sortLabel}</span>
            <SegmentedControl
              value={sort}
              onChange={setSort}
              options={[
                { value: "score" as const, label: t.discovery.sortScore },
                { value: "recent" as const, label: t.discovery.sortRecent },
              ]}
            />
          </div>
        </div>
      )}

      {busy && !dig && (
        <Loading label={t.discovery.digInProgress} />
      )}
      {dig && (
        <DiscoveryLeadGrid
          dig={dig}
          format={format}
          sort={sort}
        />
      )}
      {!busy && !dig && (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.readyTitle}>
          {digReady
            ? t.discovery.readyBodyReady
            : t.discovery.readyBodyNotReady}
        </EmptyState>
      )}
    </PageLayout>
  );
}

export default function DiscoveryPage() {
  return (
    <Suspense>
      <DiscoveryInner />
    </Suspense>
  );
}
