"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, Download as DownloadIcon, X } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, EqMeter, Loading } from "@/components/ui";
import {
  cancelQueueItem, cancelQueued, clearQueueDone, downloadQueue, errText,
  moveQueueItemTop, type QueueItem, type QueuePause, type QueueSnapshot,
} from "@/lib/api";
import { useT, type Dictionary } from "@/lib/i18n";

const LIVE_MS = 2000;   // c'e' roba viva: si guarda spesso
const IDLE_MS = 10000;  // coda ferma: basta un'occhiata ogni tanto

// Componenti a livello di modulo, non dentro DownloadsPage: dichiararli a
// render-time fa perdere lo stato locale ad ogni giro e lo linter (regola
// react-hooks/static-components) lo segnala come errore.
function QueueRow({ item, t, busy, onTop, onCancel }: {
  item: QueueItem;
  t: Dictionary;
  busy: boolean;
  onTop: (id: number) => void;
  onCancel: (id: number) => void;
}) {
  const pct = item.bytes_total ? Math.round((item.bytes_done ?? 0) / item.bytes_total * 100) : null;
  const OUTCOME: Record<string, string> = {
    downloaded: t.queue.outcomeDownloaded,
    needs_review: t.queue.outcomeNeedsReview,
    not_found: t.queue.outcomeNotFound,
    failed: t.queue.outcomeFailed,
  };
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm">
      <div className="min-w-0 flex-1">
        <div className="truncate">{item.label}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
          {item.phase === "searching" && <span>{t.queue.phaseSearching}</span>}
          {item.phase === "downloading" && <span>{t.queue.phaseDownloading}</span>}
          {pct !== null && <EqMeter value={pct} className="h-1.5 w-24" />}
          {item.attempts > 1 && <span>{t.queue.attemptsLabel(item.attempts)}</span>}
          {item.error && <span className="truncate">{item.error}</span>}
        </div>
      </div>
      <span className="flex shrink-0 items-center gap-2">
        {item.state === "cancelled" && <Badge tone="neutral">{t.queue.stateCancelled}</Badge>}
        {item.outcome && (
          <Badge tone={item.outcome === "downloaded" ? "neutral"
            : item.outcome === "failed" ? "danger" : "warning"}>
            {OUTCOME[item.outcome]}
          </Badge>
        )}
        {item.state === "queued" && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onTop(item.id)}>
            <ArrowUp size={13} /> {t.queue.topButton}
          </Button>
        )}
        {(item.state === "queued" || item.state === "running") && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onCancel(item.id)}>
            <X size={13} /> {t.queue.cancelButton}
          </Button>
        )}
      </span>
    </li>
  );
}

function QueueSection({ heading, rows, t, busy, onTop, onCancel, action }: {
  heading: string;
  rows: QueueItem[];
  t: Dictionary;
  busy: boolean;
  onTop: (id: number) => void;
  onCancel: (id: number) => void;
  action?: ReactNode;
}) {
  if (rows.length === 0) return null;
  return (
    <section>
      <div className="mb-2 flex items-center gap-3">
        <div className="text-[10px] uppercase tracking-wider text-muted">{heading}</div>
        {action}
      </div>
      <Card>
        <ul className="divide-y divide-border">
          {rows.map((i) => (
            <QueueRow key={i.id} item={i} t={t} busy={busy} onTop={onTop} onCancel={onCancel} />
          ))}
        </ul>
      </Card>
    </section>
  );
}

/* La coda in pausa era invisibile: item «in attesa» all'infinito e nessun posto
   dove leggere il perché. Sta in testa alla pagina perché è la cosa che spiega
   tutto il resto di quello che si vede sotto. */
function PauseBanner({ pause, t }: { pause: QueuePause; t: Dictionary }) {
  if (!pause.paused) return null;
  const secondi = pause.retry_in_seconds;
  return (
    <Alert tone="warning">
      <strong>{t.queue.pausedTitle}</strong>{" "}
      {t.queue.pausedReason(pause.reason)}{" "}
      {secondi && secondi > 0 ? t.queue.pausedRetry(secondi) : t.queue.pausedRetrySoon}
    </Alert>
  );
}

export default function DownloadsPage() {
  const t = useT();
  const [snap, setSnap] = useState<QueueSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  // Tenuta fuori dallo stato apposta: serve solo a scegliere il prossimo
  // ritardo del polling, e se fosse stato React re-innescherebbe l'effetto
  // sotto (dipendenza che cambia ad ogni fetch) rifacendo la chiamata due
  // volte per ogni giro invece di una.
  const live = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await downloadQueue({ signal });
      if (alive.current) {
        setSnap(s);
        setError(null);
        live.current = s.items.some((i) => i.state === "running" || i.state === "queued");
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError" && alive.current) setError(errText(e));
    }
  }, []);

  // Si auto-ripianifica ad ogni giro invece di usare un setInterval fisso:
  // il ritmo si adatta (LIVE_MS con roba viva, IDLE_MS a coda ferma) senza
  // dover rimontare l'effetto — che gira una sola volta, mount->unmount.
  useEffect(() => {
    const ac = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      await load(ac.signal);
      if (!stopped) timer = setTimeout(tick, live.current ? LIVE_MS : IDLE_MS);
    };
    tick();
    return () => { stopped = true; ac.abort(); clearTimeout(timer); };
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    let actionError: string | null = null;
    try { await fn(); } catch (e) { actionError = errText(e); }
    // La coda va ricaricata anche quando l'azione fallisce (es. 409 perche'
    // l'item e' gia' stato concluso nel frattempo): altrimenti resta a
    // schermo uno stato superato accanto al messaggio d'errore. load()
    // azzera error in caso di successo, quindi lo riapplichiamo dopo se
    // l'azione e' effettivamente fallita.
    await load();
    if (actionError && alive.current) setError(actionError);
    if (alive.current) setBusy(false);
  };

  const items = snap?.items ?? [];
  const running = items.filter((i) => i.state === "running");
  const waiting = items.filter((i) => i.state === "queued");
  // Sezioni separate, non un'unica fascia "Fatte": lo storico dei conclusi
  // e quello degli annullati vivono su endpoint diversi (svuota-storico
  // rimuove solo i "done", per design — un annullo resta a schermo finche'
  // l'utente non lo tocca), quindi devono anche essere due liste distinte —
  // altrimenti il bottone "Svuota lo storico" lascerebbe a schermo roba
  // che sembrava dover sparire.
  const done = items.filter((i) => i.state === "done");
  const cancelled = items.filter((i) => i.state === "cancelled");

  const onTop = (id: number) => act(() => moveQueueItemTop(id));
  const onCancel = (id: number) => act(() => cancelQueueItem(id));

  return (
    <PageLayout title={t.queue.pageTitle}
      meta={snap ? t.queue.slotsInUse(snap.active, snap.slots) : undefined}>
      <div className="space-y-6">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {snap?.pause && <PauseBanner pause={snap.pause} t={t} />}
        {snap === null && <Loading />}
        {snap !== null && items.length === 0 && (
          <EmptyState icon={<DownloadIcon size={28} />} title={t.queue.emptyTitle}>
            {t.queue.emptyBody}
          </EmptyState>
        )}
        <QueueSection heading={t.queue.runningHeading} rows={running} t={t} busy={busy}
          onTop={onTop} onCancel={onCancel} />
        <QueueSection heading={t.queue.waitingHeading} rows={waiting} t={t} busy={busy}
          onTop={onTop} onCancel={onCancel}
          action={
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => cancelQueued())}>
              {t.queue.cancelAllButton}
            </Button>
          } />
        <QueueSection heading={t.queue.doneHeading} rows={done} t={t} busy={busy}
          onTop={onTop} onCancel={onCancel}
          action={
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => clearQueueDone())}>
              {t.queue.clearDoneButton}
            </Button>
          } />
        <QueueSection heading={t.queue.cancelledHeading} rows={cancelled} t={t} busy={busy}
          onTop={onTop} onCancel={onCancel} />
      </div>
    </PageLayout>
  );
}
