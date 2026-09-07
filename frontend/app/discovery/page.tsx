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
  getDiscoverySettings,
  getLabels,
  searchTracks,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type DiscoverySimilarResponse,
  type LabelStats,
  type Track,
  type TrackDetail,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { applyLens, DiscoveryLeadGrid, FORMAT_VALUES, type SortMode } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar, type DigMode } from "@/components/discovery-dig-bar";
import { DiscoverySimilarHeader } from "@/components/discovery-similar-header";
import { similarHref, WINDOW_ITEMS, type DigSourceKey } from "@/lib/discovery-dig";
import { digHref, parseSeeds, sameSeeds, type DigSeed } from "@/lib/discovery-seeds";
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

  const initialDepthRaw = Number(searchParams.get("depth") ?? "0");
  const initialDepth = Number.isFinite(initialDepthRaw) ? Math.min(1, Math.max(0, initialDepthRaw)) : 0;
  const initialSource: DigSourceKey =
    searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  // `null` = preferenza non ancora letta: lo scavo aspetta, perché un URL con
  // source=discogs a Discogs spento deve degradare a Bandcamp PRIMA di partire.
  const [discogsEnabled, setDiscogsEnabled] = useState<boolean | null>(null);

  // I semi in barra: stato locale, la verità dello scavo è nell'URL (`seeds=`).
  const [seeds, setSeeds] = useState<DigSeed[]>(() => parseSeeds(searchParams.get("seeds")));
  const [depth, setDepth] = useState(initialDepth);
  const [source, setSource] = useState<DigSourceKey>(initialSource);
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

  // Modalità simili: stessa pagina, altro ramo. La verità sta nell'URL
  // (`?similar=<id>&style_period=<0|1>`) come per lo scavo, così il bottone nel
  // dettaglio traccia e l'interruttore qui dentro passano dallo stesso posto.
  const similarIdRaw = Number(searchParams.get("similar") ?? "");
  const similarId = Number.isFinite(similarIdRaw) ? similarIdRaw : 0;
  const isSimilar = similarId > 0;
  const urlStylePeriod = searchParams.get("style_period") === "1";
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

  // Il modo è stato locale: commutarlo cambia solo quale campo si vede. L'URL
  // si muove quando parte una ricerca. All'apertura si deduce da cosa c'è.
  const [mode, setMode] = useState<DigMode>(isSimilar ? "track" : "seeds");
  // L'interruttore vive nell'URL quando c'è una traccia (come prima), in locale
  // prima di sceglierla: così si accende PRIMA di cercare e viaggia col push.
  const [localStylePeriod, setLocalStylePeriod] = useState(urlStylePeriod);
  const stylePeriod = isSimilar ? urlStylePeriod : localStylePeriod;

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
    getDiscoveryGenres().then(setGenres).catch(() => setGenres({ library: [], styles: [], library_counts: [] }));
    getLabels().then(setLabels).catch(() => setLabels([]));
    getDiscoverySettings()
      .then((s) => setDiscogsEnabled(s.discogs_enabled))
      .catch(() => setDiscogsEnabled(true));
  }, []);

  const executeDig = useCallback(
    async (list: DigSeed[], d: number, src: DigSourceKey) => {
      setBusy(true);
      setError(null);
      setDig(null);
      const sourceName = src === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `${sourceName} · ${list.map((s) => s.value).join(", ")}` });
      try {
        setDig(await discoveryDig(list, { depth: d, source: src }));
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
    if (discogsEnabled === null) return;   // la preferenza decide la sorgente: si aspetta
    const list = parseSeeds(searchParams.get("seeds"));
    if (list.length === 0) return;         // pagina aperta senza uno scavo: empty state
    const depthRaw = Number(searchParams.get("depth") ?? "0");
    const d = Number.isFinite(depthRaw) ? Math.min(1, Math.max(0, depthRaw)) : 0;
    const wanted: DigSourceKey = searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
    // Discogs spento: un link con source=discogs degrada, non fallisce. Il
    // confronto è `=== false`, non `!discogsEnabled`: quest'ultimo sarebbe
    // vero anche a `null`, rendendo il ramo di degrado indipendente dalla
    // guardia sopra (e quindi dalla preferenza) invece che dipendente da essa.
    const src: DigSourceKey = discogsEnabled === false && wanted === "discogs" ? "bandcamp" : wanted;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(list, d, src);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey, discogsEnabled]);

  // A Discogs spento la barra offre solo Bandcamp: la sorgente locale si
  // allinea, così il prossimo Scava non scrive un source che la barra non mostra.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- allinea `source` alla preferenza Discogs, che arriva async dal backend (external system): non un loop di stato, la guardia sui valori la rende idempotente
    if (discogsEnabled === false && source === "discogs") setSource("bandcamp");
  }, [discogsEnabled, source]);

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
      // Entrare in una NUOVA traccia simile mostra sempre la barra in modo
      // traccia, anche se si arrivava da uno scavo lasciato in modo semi:
      // "entrare in ?similar=" è un evento, non solo lo stato al primo mount.
      setMode("track");
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
    setLocalStylePeriod(on);
    if (isSimilar) router.push(similarHref(similarId, on, from), { scroll: false });
  };

  const runDig = () => {
    if (seeds.length === 0) return;
    surpriseRef.current = false;
    surpriseRerolledRef.current = false;
    const href = digHref(pathname, seeds, depth, source);
    // Stesso URL: ricerca deterministica, stesso risultato. Niente voce doppia
    // nella cronologia.
    if (href === `${pathname}?${searchParams.toString()}`) return;
    router.push(href, { scroll: false });
  };

  const navigateDig = (seed: DigSeed, d: number) => {
    // Sorprendimi (e il reroll) mettono UN seme in barra e aggiornano l'URL: il
    // componente non rimonta, quindi lo state va allineato a mano. La sorgente
    // resta quella scelta: si pesca un seme, non una sorgente.
    setSeeds([seed]);
    setDepth(d);
    router.push(digHref(pathname, [seed], d, source), { scroll: false });
  };

  const runSurprise = () => {
    const pick = pickSurprise(surprisePool, seeds.map((s) => s.value));
    if (!pick) return;
    surpriseRef.current = true;
    surpriseRerolledRef.current = false;
    navigateDig({ type: pick.seedType, value: pick.value }, pick.depth);
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
    const pick = pickSurprise(surprisePool, dig.seeds.map((s) => s.value));
    if (!pick) return;
    surpriseRef.current = true; // anche il reroll nasce da Sorprendimi
    // navigateDig risincronizza la barra (semi/profondità) col nuovo seme
    // pescato dal reroll, non un loop di stato
    // eslint-disable-next-line react-hooks/set-state-in-effect
    navigateDig({ type: pick.seedType, value: pick.value }, pick.depth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dig]);

  // Le pile valgono per i semi CORRENTI in barra: cambiato un seme, la
  // profondità torna attiva finché non si riscava.
  const piles = dig && sameSeeds(dig.seeds, seeds) ? dig.piles : null;

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

  // Zero lead nello scavo ha due cause diverse, e dirle uguali mente. Se una pila
  // non esiste (`total === 0`) quel seme è sconosciuto alla sorgente: la
  // libreria non c'entra e "vai più a fondo" è un consiglio che non può
  // funzionare, perché non c'è fondo. Se invece le pile ci sono, i dischi sono
  // stati filtrati (li possiedi già) e scavare più a fondo è la mossa giusta.
  const digEmpty = (d: DiscoveryDigResponse) => {
    const srcName = d.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
    const names = d.seeds.map((s) => `“${s.value}”`).join(", ");
    const live = d.piles.filter((p) => p.total > 0);
    if (live.length === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.deadSeedTitle(srcName)}>
          {t.discovery.deadSeedBody(names, srcName)}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      const budget = Math.floor(WINDOW_ITEMS / Math.max(1, d.seeds.length));
      const shortPile = live.every((p) => p.reach <= budget);
      // Solo i semi VIVI qui: quelli morti li nomina già l'avviso della barra,
      // ripeterli in questo messaggio mentirebbe su quali hanno una pila.
      const liveNames = live.map((p) => `“${p.value}”`).join(", ");
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
          {shortPile ? t.discovery.nothingToDigShortPile(liveNames) : t.discovery.nothingToDigSeeds(liveNames)}
        </EmptyState>
      );
    }
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

      <DiscoveryDigBar
        mode={mode}
        onModeChange={setMode}
        seeds={seeds}
        onSeedsChange={setSeeds}
        depth={depth}
        onDepthChange={setDepth}
        source={source}
        onSourceChange={setSource}
        discogsEnabled={discogsEnabled !== false}
        stylePeriod={stylePeriod}
        onStylePeriodChange={setStylePeriod}
        options={{
          genres: genres ?? { library: [], styles: [] },
          labels: labels?.map((l) => l.label) ?? [],
          genreCounts: genres?.library_counts ?? [],
        }}
        piles={piles}
        busy={busy}
        onSubmit={runDig}
        onSurprise={runSurprise}
        canSurprise={canSurprise}
        onPickTrack={(track: Track) => router.push(similarHref(track.id, stylePeriod, null), { scroll: false })}
        searchTracks={searchTracks}
      />

      {isSimilar && sim && simTrack && (
        <DiscoverySimilarHeader data={sim} track={simTrack} />
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
          {!isSimilar && dig && dig.piles.some((p) => p.total > p.reach) && (
            <span className="tnum text-muted">
              {t.discovery.broadSeeds(
                dig.piles
                  .filter((p) => p.total > p.reach)
                  .map((p) => t.discovery.broadSeedDetail(
                    p.value, p.total.toLocaleString(lang), p.reach.toLocaleString(lang)))
                  .join("; "),
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
          {seeds.length > 0
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
