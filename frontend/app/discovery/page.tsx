"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Disc3 } from "lucide-react";
import {
  apiGet,
  discoveryDig,
  discoverySimilar,
  errText,
  getDiscoveryGenres,
  getLabels,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type DiscoverySimilarResponse,
  type LabelStats,
  type TrackDetail,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { applyLens, DiscoveryLeadGrid, FORMAT_VALUES, type SortMode } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar } from "@/components/discovery-dig-bar";
import { DiscoverySimilarHeader } from "@/components/discovery-similar-header";
import { similarHref, WINDOW_ITEMS, type DigSourceKey, type SeedType } from "@/lib/discovery-dig";
import { isInternalPath, withFrom } from "@/lib/back-link";
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

  // Modalità simili: stessa pagina, altro ramo. La verità sta nell'URL
  // (`?similar=<id>&style_period=<0|1>`) come per lo scavo, così il bottone nel
  // dettaglio traccia e l'interruttore qui dentro passano dallo stesso posto.
  const similarIdRaw = Number(searchParams.get("similar") ?? "");
  const similarId = Number.isFinite(similarIdRaw) ? similarIdRaw : 0;
  const isSimilar = similarId > 0;
  const stylePeriod = searchParams.get("style_period") === "1";
  // L'origine da cui si è arrivati alla traccia, di passaggio qui: serve al link
  // indietro per restituire la traccia con la sua memoria (i filtri della
  // libreria, la playlist) invece che nuda. Validata perché finisce dentro un
  // href, e chi scrive l'URL non è per forza l'app.
  const fromRaw = searchParams.get("from");
  const from = fromRaw && isInternalPath(fromRaw) ? fromRaw : null;
  const similarBackHref = from
    ? withFrom(`/tracks?id=${similarId}`, from)
    : `/tracks?id=${similarId}`;
  const [sim, setSim] = useState<DiscoverySimilarResponse | null>(null);
  const [simTrack, setSimTrack] = useState<TrackDetail | null>(null);
  // Traccia dell'ultimo giro dei simili. Distingue le due ragioni per cui
  // l'effect riparte: un id diverso è un altro soggetto (il risultato di prima
  // non lo descrive più: si azzera e parte lo spinner), mentre l'interruttore
  // stile/periodo sulla STESSA traccia è solo un'altra domanda sullo stesso
  // soggetto. Lì il risultato resta montato, altrimenti l'intestazione (e il
  // suo interruttore) sparirebbe da sotto il cursore proprio mentre `busy`
  // dovrebbe limitarsi a disabilitarla.
  const simTrackRef = useRef<number | null>(null);

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
    // I due rami leggono la STESSA query string: senza questa guardia, entrare in
    // modalità simili farebbe partire anche un dig col valore vuoto.
    if (isSimilar) return;
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

  // Gemello del precedente per la modalità simili: stessa dipendenza (l'URL),
  // guardia opposta. La traccia di partenza serve all'intestazione (artista e
  // titolo) e va chiesta insieme ai simili, non prima: se una delle due fallisce
  // il ramo è comunque inservibile, e l'errore va mostrato una volta sola.
  useEffect(() => {
    if (!isSimilar) return;
    const trackChanged = simTrackRef.current !== similarId;
    simTrackRef.current = similarId;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- i simili sono l'external system: l'effect risincronizza il risultato sull'URL (query string), non su state locale
    setBusy(true);
    setError(null);
    if (trackChanged) {
      setSim(null);
      setSimTrack(null);
    }
    jobs.startClientJob("dig", t.discovery.similarJob);
    Promise.all([
      discoverySimilar(similarId, { stylePeriod }),
      apiGet<TrackDetail>(`/api/tracks/${similarId}`),
    ])
      .then(([data, track]) => {
        setSim(data);
        setSimTrack(track);
        jobs.updateClientJob("dig", { detail: `${track.artist} — ${track.title}` });
      })
      .catch((e) => setError(errText(e)))
      .finally(() => {
        setBusy(false);
        jobs.endClientJob("dig");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  // L'interruttore stile/periodo riscrive l'URL come fanno i parametri dello
  // scavo: `similarHref` è la stessa funzione che scrive il bottone nel dettaglio
  // traccia, così un solo posto costruisce questo indirizzo.
  const setStylePeriod = (on: boolean) => {
    // `from` deve sopravvivere al giro dell'interruttore, altrimenti la catena
    // indietro si spezza al primo clic invece che al primo passo indietro.
    router.push(similarHref(similarId, on, from), { scroll: false });
  };

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

  // `hasResult` guarda solo la modalità corrente: un `sim` rimasto in memoria da
  // prima non deve far comparire la riga delle lenti (né spegnere lo spinner)
  // mentre è in corso uno scavo, e viceversa.
  const hasResult = isSimilar ? sim !== null : dig !== null;

  // Lista e conteggio escono dalla STESSA lente: "40 di 240" e le 40 card mostrate
  // non possono divergere. Il taglio (`show`) viene dopo il filtro di formato.
  // La lente vale per entrambe le modalità: cambia solo da dove arrivano i lead.
  const { visible, total } = useMemo(
    () => applyLens(isSimilar ? sim?.leads ?? [] : dig?.leads ?? [], { format, sort, show }),
    [isSimilar, sim, dig, format, sort, show],
  );

  // Zero lead nello scavo ha due cause diverse, e dirle uguali mente. Se la pila
  // non esiste (`pile_total === 0`) il seme è sconosciuto alla sorgente: la
  // libreria non c'entra e "vai più a fondo" è un consiglio che non può
  // funzionare, perché non c'è fondo. Se invece la pila c'è, i dischi sono stati
  // filtrati (li possiedi già) e scavare più a fondo è la mossa giusta.
  const digEmpty = (d: DiscoveryDigResponse) => {
    // Nome leggibile della sorgente di QUESTO dig, non di quella selezionata ora
    // nella barra: le stringhe non devono mentire su un risultato precedente.
    const srcName = d.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
    if (d.pile_total === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.deadSeedTitle(srcName)}>
          {t.discovery.deadSeedBody(d.value, srcName)}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      // Su una pila CORTA (la finestra è l'intera pila) "vai più a fondo" è un
      // consiglio inerte — la profondità è disabilitata proprio per quella pila.
      const shortPile = d.pile_reach <= WINDOW_ITEMS;
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
          {shortPile
            ? t.discovery.nothingToDigShortPile(d.value)
            : t.discovery.nothingToDigBody(
                d.value,
                d.seed_type === "label" ? t.discovery.seedTypeValue : t.discovery.seedTypeStyle,
              )}
        </EmptyState>
      );
    }
    // Lead ce ne sono: se la lista è vuota è la lente di formato ad averli tolti.
    return <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>;
  };

  // I simili hanno le loro cause, diverse da quelle dello scavo: nessun punto di
  // partenza (Bandcamp non conosce l'artista) contro parentela trovata ma tutta
  // già posseduta. Il guasto della sorgente non passa di qui: è un errore, e
  // sale nell'alert in cima alla pagina.
  const similarEmpty = (d: DiscoverySimilarResponse) => {
    if (!d.origin) {
      return (
        <EmptyState
          icon={<Disc3 size={28} />}
          title={t.discovery.similarNoBandTitle(simTrack?.artist ?? "")}
        >
          {t.discovery.similarNoBandBody}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.similarAllOwnedTitle}>
          {t.discovery.similarAllOwnedBody(d.origin.artist)}
          {!stylePeriod && ` ${t.discovery.similarAllOwnedHint}`}
        </EmptyState>
      );
    }
    return <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>;
  };

  return (
    <PageLayout title="Dig">
      {/* In cima e a sinistra come in ogni pagina di dettaglio, e fuori
          dall'intestazione dei risultati di proposito: una ricerca di simili
          dura una decina di secondi, e per tornare indietro non si deve
          aspettare che finisca. */}
      {isSimilar && (
        <Link href={similarBackHref}
              className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
          <ArrowLeft size={15} /> {t.discovery.similarBackToTrack}
        </Link>
      )}

      <p className="mb-4 text-sm text-muted">
        {isSimilar ? t.discovery.similarIntro : t.discovery.intro}
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {isSimilar && sim && simTrack && (
        <DiscoverySimilarHeader
          data={sim}
          track={simTrack}
          backHref={similarBackHref}
          stylePeriod={stylePeriod}
          onStylePeriodChange={setStylePeriod}
          busy={busy}
        />
      )}

      {!isSimilar && (
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
      )}

      {hasResult && (
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
          {/* La pila è roba dello scavo: i simili non ne hanno una, quindi questo
              avviso resta legato a `dig`. Serve ANCHE `!isSimilar`: `dig` non
              viene azzerato entrando nei simili, e uno scavo largo lasciato
              indietro (scavo → back su `?similar=…`) descriverebbe qui una pila
              che questa vista non ha. */}
          {!isSimilar && dig && dig.pile_total > dig.pile_reach && (
            <span className="tnum text-muted">
              {/* Sul seme etichetta il consiglio "un sottogenere più preciso" non ha
                  senso (una label non è un genere): variante senza quella frase. */}
              {(dig.seed_type === "label" ? t.discovery.broadSeedLabel : t.discovery.broadSeed)(
                dig.pile_total.toLocaleString(lang),
                dig.pile_reach.toLocaleString(lang),
                dig.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs,
              )}
            </span>
          )}
        </div>
      )}

      {busy && !hasResult && (
        <Loading label={isSimilar ? t.discovery.similarInProgress : t.discovery.digInProgress} />
      )}
      {isSimilar
        ? sim && <DiscoveryLeadGrid leads={visible} empty={similarEmpty(sim)} />
        : dig && <DiscoveryLeadGrid leads={visible} empty={digEmpty(dig)} />}
      {/* L'invito a scavare vale solo per la barra: in modalità simili non c'è
          niente da digitare, e lo stato vuoto lo dà `similarEmpty`. */}
      {!isSimilar && !busy && !dig && (
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
