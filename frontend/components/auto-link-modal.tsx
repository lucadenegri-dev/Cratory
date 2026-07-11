"use client";

import { useEffect, useState } from "react";
import { FolderOpen, Link2 } from "lucide-react";
import { Alert, Button, Loading, Modal, Spinner } from "@/components/ui";
import { autoLinkPreview, linkLocalFile, type AutoLinkProposal } from "@/lib/api";
import { useT, type Dictionary } from "@/lib/i18n";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function sourceLabel(t: Dictionary): Record<string, string> {
  return { library: t.tracks.sourceLibrary, downloads: t.tracks.sourceDownloads };
}

/** Wrapper: monta il dialog solo da aperto e lo rigenera a ogni apertura. */
export function AutoLinkModal({ open, onClose, onLinked }: {
  open: boolean;
  onClose: () => void;
  onLinked: () => void;
}) {
  if (!open) return null;
  return <Dialog onClose={onClose} onLinked={onLinked} />;
}

/** "Collega file automatico": propone un file locale per ogni traccia da sistemare,
    l'utente deseleziona i match sbagliati e conferma (il collegamento vero è per-traccia). */
function Dialog({ onClose, onLinked }: { onClose: () => void; onLinked: () => void }) {
  const t = useT();
  const SOURCE_LABEL = sourceLabel(t);
  const [proposals, setProposals] = useState<AutoLinkProposal[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [linking, setLinking] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    autoLinkPreview()
      .then((p) => {
        if (!alive) return;
        setProposals(p);
        setSelected(new Set(p.filter((x) => x.hit).map((x) => x.track_id)));
      })
      .catch((e) => { if (alive) { setError(err(e)); setProposals([]); } });
    return () => { alive = false; };
  }, []);

  const withHit = (proposals ?? []).filter((p) => p.hit);
  const noHit = (proposals ?? []).length - withHit.length;

  const toggle = (id: number) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  const apply = async () => {
    setLinking(true); setError(null); setDone(0);
    const chosen = withHit.filter((p) => selected.has(p.track_id));
    let ok = 0;
    for (const p of chosen) {
      try {
        await linkLocalFile(p.track_id, p.hit!.path);
        ok += 1; setDone(ok);
      } catch (e) {
        setError(err(e));  // un fallimento non ferma le altre
      }
    }
    setLinking(false);
    onLinked();
    if (ok === chosen.length) onClose();  // tutte collegate: chiudi
  };

  const footer = (
    <Button onClick={apply} disabled={linking || selected.size === 0}>
      {linking ? <Spinner /> : <Link2 size={13} />} {t.tracks.linkSelected(selected.size)}
    </Button>
  );

  return (
    <Modal open onClose={onClose} title={t.tracks.autoLinkTitle} size="lg" footer={footer}>
      <div className="space-y-3 p-4">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {proposals === null && <Loading label={t.tracks.searchingDisk} />}
        {proposals !== null && withHit.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">
            {t.tracks.noAutoMatches}
          </p>
        )}
        {withHit.length > 0 && (
          <>
            <p className="text-xs text-muted">
              {t.tracks.autoLinkSummary(withHit.length, noHit)}
            </p>
            <ul className="max-h-96 divide-y divide-border overflow-y-auto border border-border">
              {withHit.map((p) => (
                <li key={p.track_id} className="flex items-start gap-3 px-3 py-2 text-sm">
                  <input
                    type="checkbox" checked={selected.has(p.track_id)}
                    onChange={() => toggle(p.track_id)} disabled={linking}
                    className="mt-1 h-4 w-4 accent-[var(--color-fg)]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{p.label}</div>
                    <div className="mt-0.5 truncate font-mono text-xs text-muted">
                      <FolderOpen size={11} className="mr-1 inline" />
                      {p.hit!.name}
                      <span className="text-faint">
                        {" · "}{SOURCE_LABEL[p.hit!.source] ?? p.hit!.source}
                        {p.hit!.size ? ` · ${fmtSize(p.hit!.size)}` : ""}
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            {linking && <p className="tnum text-xs text-muted">{t.tracks.linkedProgress(done, selected.size)}</p>}
          </>
        )}
      </div>
    </Modal>
  );
}
