"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Disc3 } from "lucide-react";
import {
  discoveryDig,
  errText,
  getDiscoveryGenres,
  getLabels,
  DISCOGS_PAGE_SIZE,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type LabelStats,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { applyLens, DiscoveryLeadGrid, FORMAT_VALUES, type SortMode } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar, type SeedType } from "@/components/discovery-dig-bar";
import { useI18n } from "@/lib/i18n";

function DiscoveryInner() {
  // `lang` serve al formato dei numeri: toLocaleString() senza argomento segue il
  // locale del BROWSER, non la lingua scelta in-app — "4,960,096" dentro una frase
  // italiana. Coi tag "it"/"en" i separatori seguono la lingua dell'interfaccia.
  const { t, lang } = useI18n();
  const jobs = useJobs();

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialSeed = (searchParams.get("seed") === "label" ? "label" : "genre") as SeedType;
  const initialValue = searchParams.get("value") ?? "";
  const initialDepthRaw = Number(searchParams.get("depth") ?? "0");
  const initialDepth = Number.isFinite(initialDepthRaw) ? Math.min(1, Math.max(0, initialDepthRaw)) : 0;
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [labels, setLabels] = useState<LabelStats[] | null>(null);

  // scava (dig Discogs) — il soggetto (genere o etichetta) è un unico campo:
  // il seed_type è derivato da quale gruppo dell'autocomplete è stato scelto.
  const [seedType, setSeedType] = useState<SeedType>(initialSeed);
  const [subject, setSubject] = useState(initialValue);
  const [depth, setDepth] = useState(initialDepth);
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

  // lenti sui risultati già ottenuti: fuori dall'URL, non rilanciano il dig
  const [format, setFormat] = useState<string | null>(null);
  const [sort, setSort] = useState<SortMode>("score");
  const [show, setShow] = useState<number | "all">(80);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiscoveryGenres()
      .then(setGenres)
      .catch(() => setGenres({ library: [], styles: [] }));
    getLabels()
      .then(setLabels)
      .catch(() => setLabels([]));
  }, []);

  const executeDig = useCallback(
    async (seed: SeedType, value: string, d: number) => {
      setBusy(true);
      setError(null);
      setDig(null);
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `Discogs · ${value}` });
      try {
        setDig(await discoveryDig(seed, value, { depth: d }));
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(seed, value, d);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const runDig = () => {
    const value = subject.trim();
    if (!value) return;
    const params = new URLSearchParams();
    params.set("seed", seedType);
    params.set("value", value);
    params.set("depth", String(depth));
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

  // Lista e conteggio escono dalla STESSA lente: "40 di 240" e le 40 card mostrate
  // non possono divergere. Il taglio (`show`) viene dopo il filtro di formato.
  const { visible, total } = useMemo(
    () => applyLens(dig?.leads ?? [], { format, sort, show }),
    [dig, format, sort, show],
  );

  return (
    <PageLayout title="Dig">
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
        options={{
          genres: genres ?? { library: [], styles: [] },
          labels: labels?.map((l) => l.label) ?? [],
        }}
        pilePages={pilePages}
        busy={busy}
        ready={digReady}
        onSubmit={runDig}
      />

      {dig && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border pb-3 text-xs">
          <span className="tnum text-muted">
            {visible.length < total
              ? t.discovery.leadCountOf(visible.length, total)
              : t.discovery.leadCount(total)}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.showLabel}</span>
            <SegmentedControl
              value={show === "all" ? "all" : String(show)}
              onChange={(v) => setShow(v === "all" ? "all" : Number(v))}
              options={[
                { value: "40", label: "40" },
                { value: "80", label: "80" },
                { value: "all", label: t.discovery.showAll },
              ]}
            />
          </div>
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
          {dig.seed_resolution === "genre" && dig.pile_total > dig.pile_pages * DISCOGS_PAGE_SIZE && (
            // Il seme e' ripiegato sullo scaffale Discogs (~15 categorie enormi):
            // la pila raggiungibile e' una briciola del totale, e va detto. La guardia
            // sul totale evita di dire "ne vedi solo N" quando la pila e' tutta li'.
            <span className="tnum text-muted">
              {t.discovery.broadSeed(
                dig.pile_total.toLocaleString(lang),
                (dig.pile_pages * DISCOGS_PAGE_SIZE).toLocaleString(lang),
              )}
            </span>
          )}
        </div>
      )}

      {busy && !dig && (
        <Loading label={t.discovery.digInProgress} />
      )}
      {dig && (
        <DiscoveryLeadGrid dig={dig} leads={visible} />
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
