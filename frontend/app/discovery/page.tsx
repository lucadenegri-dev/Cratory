"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Disc3 } from "lucide-react";
import {
  discoveryDig,
  errText,
  getDiscoveryGenres,
  getLabels,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type LabelStats,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { applyLens, DiscoveryLeadGrid, FORMAT_VALUES, type SortMode } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar } from "@/components/discovery-dig-bar";
import { type DigSourceKey, type SeedType } from "@/lib/discovery-dig";
import { pickSurprise } from "@/lib/discovery-surprise";
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
  const initialSource: DigSourceKey =
    searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [labels, setLabels] = useState<LabelStats[] | null>(null);

  // scava (dig Discogs) — il soggetto (genere o etichetta) è un unico campo:
  // il seed_type è derivato da quale gruppo dell'autocomplete è stato scelto.
  const [seedType, setSeedType] = useState<SeedType>(initialSeed);
  const [subject, setSubject] = useState(initialValue);
  const [depth, setDepth] = useState(initialDepth);
  const [source, setSource] = useState<DigSourceKey>(initialSource);
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

  // lenti sui risultati già ottenuti: fuori dall'URL, non rilanciano il dig
  const [format, setFormat] = useState<string | null>(null);
  const [sort, setSort] = useState<SortMode>("score");
  const [show, setShow] = useState<number | "all">(80);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "Sorprendimi": traccia se il dig in corso nasce dal bottone (per il reroll)
  // e se il reroll singolo è già stato speso.
  const surpriseRef = useRef(false);
  const surpriseRerolledRef = useRef(false);

  const surprisePool = useMemo(
    () => ({ genres: genres?.library ?? [], labels: labels?.map((l) => l.label) ?? [] }),
    [genres, labels],
  );
  const canSurprise = surprisePool.genres.length + surprisePool.labels.length > 0;

  useEffect(() => {
    getDiscoveryGenres()
      .then(setGenres)
      .catch(() => setGenres({ library: [], styles: [] }));
    getLabels()
      .then(setLabels)
      .catch(() => setLabels([]));
  }, []);

  const executeDig = useCallback(
    async (seed: SeedType, value: string, d: number, src: DigSourceKey) => {
      setBusy(true);
      setError(null);
      setDig(null);
      const sourceName = src === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `${sourceName} · ${value}` });
      try {
        setDig(await discoveryDig(seed, value, { depth: d, source: src }));
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
    const src: DigSourceKey = searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(seed, value, d, src);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const runDig = () => {
    const value = subject.trim();
    if (!value) return;
    surpriseRef.current = false;
    surpriseRerolledRef.current = false;
    const params = new URLSearchParams();
    params.set("seed", seedType);
    params.set("value", value);
    params.set("depth", String(depth));
    params.set("source", source);
    // Params identici a quelli già nell'URL: la ricerca è deterministica, il
    // risultato sarebbe lo stesso. Non pushare, così non si accumula una voce
    // di cronologia duplicata (back richiederebbe due click).
    if (params.toString() === searchParams.toString()) return;
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const navigateDig = (seed: SeedType, value: string, d: number) => {
    // Sincronizza la barra col seme pescato: "Sorprendimi" (e il reroll) aggiornano
    // l'URL ma il componente non rimonta, quindi lo state va allineato a mano perché
    // Combobox e profondità mostrino cosa è uscito. La sorgente NON cambia: "Sorprendimi"
    // pesca un seme, non una sorgente, quindi resta quella già selezionata (closure `source`).
    setSeedType(seed);
    setSubject(value);
    setDepth(d);
    const params = new URLSearchParams();
    params.set("seed", seed);
    params.set("value", value);
    params.set("depth", String(d));
    params.set("source", source);
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const runSurprise = () => {
    const pick = pickSurprise(surprisePool, subject.trim() || null);
    if (!pick) return;
    surpriseRef.current = true;        // questo dig nasce da Sorprendimi
    surpriseRerolledRef.current = false; // nuovo click: reroll di nuovo disponibile
    navigateDig(pick.seedType, pick.value, pick.depth);
  };

  // Colpo a vuoto di "Sorprendimi": un solo reroll automatico, poi l'empty state
  // normale. Vale solo per i dig nati dal bottone (surpriseRef), mai per i manuali.
  useEffect(() => {
    if (!dig) return;
    if (!surpriseRef.current) return;
    surpriseRef.current = false; // consuma il flag del dig appena risolto
    if (dig.leads.length > 0) return;
    if (surpriseRerolledRef.current) return; // reroll già speso: mostra empty state
    surpriseRerolledRef.current = true;
    const pick = pickSurprise(surprisePool, dig.value);
    if (!pick) return;
    surpriseRef.current = true; // anche il reroll nasce da Sorprendimi
    // navigateDig risincronizza la barra (subject/seedType/depth) col nuovo seme
    // pescato dal reroll, non un loop di stato
    // eslint-disable-next-line react-hooks/set-state-in-effect
    navigateDig(pick.seedType, pick.value, pick.depth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dig]);

  const digReady = !!subject.trim();
  // Invalida a ogni cambio di seme (soggetto o tipo): senza questo controllo `pile`
  // resta legato all'ULTIMA risposta, non al soggetto corrente digitato — il controllo
  // di profondita' restava disabilitato (pila corta di prima) finche' non si rilanciava
  // il dig, contro la spec ("disabled fino al prossimo cambio di seme").
  const pile =
    dig && dig.seed_type === seedType && dig.value === subject.trim()
      ? { total: dig.pile_total, reach: dig.pile_reach }
      : null;

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
        source={source}
        onSourceChange={setSource}
        options={{
          genres: genres ?? { library: [], styles: [] },
          labels: labels?.map((l) => l.label) ?? [],
        }}
        pile={pile}
        busy={busy}
        ready={digReady}
        onSubmit={runDig}
        onSurprise={runSurprise}
        canSurprise={canSurprise}
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
          {dig.pile_total > dig.pile_reach && (
            <span className="tnum text-muted">
              {t.discovery.broadSeed(
                dig.pile_total.toLocaleString(lang),
                dig.pile_reach.toLocaleString(lang),
                dig.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs,
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
