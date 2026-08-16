"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Download as DownloadIcon, ExternalLink, Search, Trash2 } from "lucide-react";
import { Alert, Badge, Button, Input, Loading, Modal, Spinner } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import {
  discardReview, downloadReview, enqueueDownloads, errText, fmtDuration, fmtSize,
  keepReview, slskdStatus, soulseekSearch, type DownloadCandidate, type DownloadReview,
  type SoulseekSearchFile,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

export type SoulseekSearchTarget = { track_id: number; artist: string | null; title: string | null };

/** Wrapper: monta il dialog solo con un target e lo rigenera per ogni traccia. */
export function SoulseekSearchModal({ target, onClose, onPicked }: {
  target: SoulseekSearchTarget | null;
  onClose: () => void;
  onPicked: () => void;
}) {
  if (!target) return null;
  return <SearchDialog key={target.track_id} target={target} onClose={onClose} onPicked={onPicked} />;
}

/** DownloadCandidate per POST /api/downloads/queue: score/tier non servono al
 *  download (il backend ricostruisce SlskdFile dai soli campi identita'). */
function toCandidate(f: SoulseekSearchFile): DownloadCandidate {
  return {
    username: f.username, filename: f.filename, size: f.size, bitrate: f.bitrate,
    length: f.length, format: f.format, name_score: 0, quality_tier: 0,
    confidence: f.confidence ?? 0,
  };
}

function baseName(filename: string): string {
  return filename.split("\\").pop()?.split("/").pop() ?? filename;
}

function SearchDialog({ target, onClose, onPicked }: {
  target: SoulseekSearchTarget;
  onClose: () => void;
  onPicked: () => void;
}) {
  const t = useT();
  const { download: jobStatus, refresh } = useJobs();
  // La coda parallela (B) fa restare /api/downloads/status a "running" per
  // tutta la vita della coda, non piu' per un singolo download: qui non si
  // guarda piu' `status`, solo se slskd e' configurato del tutto.
  const canDownload = jobStatus?.available ?? true;

  const [query, setQuery] = useState(`${target.artist ?? ""} ${target.title ?? ""}`.trim());
  const [variants, setVariants] = useState<string[]>([]);
  const [results, setResults] = useState<SoulseekSearchFile[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<DownloadReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Esito non-errore di «Scarica questo»: scelta sostituita, o scartata perché
  // la traccia è già in scaricamento.
  const [notice, setNotice] = useState<string | null>(null);
  // Per il link di scampo dentro l'avviso d'errore: se slskd non risponde, la
  // sua web UI e' la via d'uscita, e il link in fondo alla pagina wishlist e'
  // dietro a questo modal. web_url resta valorizzato anche a demone giu'.
  const [slskdWebUrl, setSlskdWebUrl] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  // Generazione della ricerca in corso: l'apertura lancia subito una ricerca
  // automatica e l'utente puo' rilanciarne un'altra (variante o riedit) prima
  // che la prima risponda. Le promesse possono risolversi fuori ordine (il
  // backend attende fino a 15s per ricerca): senza un contatore vincerebbe
  // l'ultima a *risolversi*, non l'ultima *lanciata*, e i risultati vecchi
  // sovrascriverebbero quelli della query che l'utente vede nel campo.
  const searchGen = useRef(0);

  const search = useCallback(async (q: string) => {
    const gen = ++searchGen.current;
    setSearching(true);
    setError(null);
    try {
      const r = await soulseekSearch(q, target.track_id);
      if (!alive.current || gen !== searchGen.current) return;
      setResults(r.results);
      if (r.variants.length > 0) setVariants(r.variants);
    } catch (e) {
      if (alive.current && gen === searchGen.current) { setError(errText(e)); setResults([]); }
    } finally {
      if (alive.current && gen === searchGen.current) setSearching(false);
    }
  }, [target.track_id]);

  // All'apertura: blocco revisione (se esiste un file dubbio) + ricerca automatica
  // con la query precompilata. La ricerca non aspetta la review: partono insieme.
  useEffect(() => {
    downloadReview(target.track_id).then((r) => alive.current && setReview(r)).catch(() => undefined);
    slskdStatus().then((s) => alive.current && setSlskdWebUrl(s.web_url)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Soulseek è l'external system: l'effect avvia subito la ricerca sul target aperto, non deriva da altro state locale
    void search(`${target.artist ?? ""} ${target.title ?? ""}`.trim());
  }, [target, search]);

  const runVariant = (v: string) => { setQuery(v); void search(v); };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try { await fn(); refresh(); onPicked(); } catch (e) { setError(errText(e)); }
    finally { if (alive.current) setBusy(false); }
  };

  /* «Scarica questo» non è come le altre azioni: il backend può SALTARE la
     richiesta (la traccia è già in scaricamento) o SOSTITUIRE il candidato di
     un item già in attesa. Chiudere il modal in tutti e tre i casi, com'era,
     fa credere all'utente che la sua scelta sia stata presa anche quando è
     stata scartata — e l'auto-pick continua per conto suo. */
  const pick = async (f: SoulseekSearchFile) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await enqueueDownloads([target.track_id], { candidate: toCandidate(f) });
      refresh();
      if (res.skipped > 0 && res.enqueued === 0 && res.replaced === 0) {
        setNotice(t.downloads.search.alreadyRunning);
        return;   // niente onPicked: il modal resta aperto sul messaggio
      }
      if (res.replaced > 0) setNotice(t.downloads.search.replacedChoice);
      onPicked();
    } catch (e) {
      setError(errText(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const expDur = review?.expected.duration_seconds ?? null;
  const dl = review?.downloaded ?? null;
  const dlDelta = expDur != null && dl?.duration_seconds != null ? dl.duration_seconds - expDur : null;

  return (
    <Modal open onClose={onClose} title={t.downloads.search.modalTitle} size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">
          {target.artist ?? "?"} — {target.title ?? "?"}
          {expDur != null && (
            <span className="ml-2 text-xs text-faint">{t.downloads.review.expectedDuration(fmtDuration(expDur))}</span>
          )}
        </p>
        {error && (
          <Alert tone="danger">
            ⚠ {error}
            {slskdWebUrl && (
              <a href={slskdWebUrl} target="_blank" rel="noopener noreferrer"
                className="ml-2 inline-flex items-center gap-1 underline">
                <ExternalLink size={12} /> {t.downloads.search.openSlskd}
              </a>
            )}
          </Alert>
        )}
        {notice && <Alert tone="info">{notice}</Alert>}

        {/* File dubbio gia' scaricato: Tieni/Scarta (endpoint review invariati). */}
        {dl && (
          <div className="border border-border-strong p-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
              {t.downloads.review.fileAlreadyDownloaded}
            </div>
            <div className="truncate font-mono text-xs">{dl.name}</div>
            <div className="mt-0.5 text-xs text-muted">
              {(dl.format ?? "?").toUpperCase()}
              {dl.bitrate ? ` · ${dl.bitrate} kbps` : ""}
              {dl.duration_seconds != null ? ` · ${fmtDuration(dl.duration_seconds)}` : ""}
              {dlDelta != null && (
                <span className="ml-1 text-fg-strong">
                  ({dlDelta > 0 ? "+" : ""}{dlDelta}s {t.downloads.review.vsExpected})
                </span>
              )}
              {dl.size ? ` · ${fmtSize(dl.size)}` : ""}
            </div>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => act(() => keepReview(target.track_id))} disabled={busy}>
                {busy ? <Spinner /> : <Check size={13} />} {t.downloads.review.keepAnywayButton}
              </Button>
              <Button size="sm" variant="danger"
                onClick={() => act(() => discardReview(target.track_id))} disabled={busy}>
                <Trash2 size={13} /> {t.downloads.review.discardButton}
              </Button>
            </div>
          </div>
        )}

        {/* Query modificabile + varianti dell'auto-pick come scorciatoie. */}
        <form className="flex items-center gap-2"
          onSubmit={(e) => { e.preventDefault(); void search(query); }}>
          <Input className="h-8 flex-1" value={query} aria-label={t.downloads.search.queryAria}
            onChange={(e) => setQuery(e.target.value)} />
          <Button type="submit" size="sm" disabled={searching || !query.trim()}>
            {searching ? <Spinner /> : <Search size={13} />} {t.downloads.search.searchButton}
          </Button>
        </form>
        {variants.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span>{t.downloads.search.variantsHint}</span>
            {variants.filter((v) => v !== query).map((v) => (
              // Disabilitati durante una ricerca come il bottone «Cerca»: ogni
              // click e' una richiesta sincrona da ~15s al backend, e impilarle
              // non porta nulla a schermo (vince comunque l'ultima lanciata).
              <button key={v} type="button" onClick={() => runVariant(v)} disabled={searching}
                className="border border-border px-1.5 py-px text-[11px] text-muted hover:text-fg disabled:opacity-50">
                {v}
              </button>
            ))}
          </div>
        )}

        {/* Risultati grezzi: il ranking ordina e marca, non esclude. */}
        {searching && results === null && <Loading label={t.downloads.search.searching} />}
        {/* Niente empty state sotto un errore: la lista e' vuota perche' la
            ricerca e' fallita, e «prova una variante piu' corta» manderebbe
            l'utente a riformulare la query mentre il problema e' il demone. */}
        {results?.length === 0 && !searching && !error && (
          <p className="py-6 text-center text-sm text-muted">{t.downloads.search.noResults}</p>
        )}
        {results && results.length > 0 && (
          <ul className="max-h-80 divide-y divide-border overflow-y-auto border border-border">
            {results.map((f, i) => {
              const delta = expDur != null && f.length != null ? f.length - expDur : null;
              return (
                <li key={`${f.username}-${f.filename}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs" title={f.filename}>{baseName(f.filename)}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {(f.format ?? "?").toUpperCase()}
                      {f.bitrate ? ` · ${f.bitrate} kbps` : ""}
                      {f.length != null ? ` · ${fmtDuration(f.length)}` : ""}
                      {delta != null && (
                        <span className="ml-1 text-fg-strong">
                          ({delta > 0 ? "+" : ""}{delta}s {t.downloads.search.vsExpected}{Math.abs(delta) > 20 ? " ⚠" : ""})
                        </span>
                      )}
                      {f.size ? ` · ${fmtSize(f.size)}` : ""}
                      {" · "}{f.username}
                      {!f.has_free_slot ? ` · ${t.downloads.search.noSlot}`
                        : (f.queue_length ?? 0) > 0 ? ` · ${t.downloads.search.queueInfo(f.queue_length ?? 0)}` : ""}
                    </div>
                  </div>
                  {f.auto_ok && <Badge tone="neutral">{t.downloads.search.autoOkBadge}</Badge>}
                  <Button size="sm" variant="outline" disabled={busy || !canDownload}
                    onClick={() => void pick(f)}>
                    {busy ? <Spinner /> : <DownloadIcon size={13} />} {t.downloads.search.downloadThis}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
