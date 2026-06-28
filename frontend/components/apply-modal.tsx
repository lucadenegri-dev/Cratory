"use client";

import { Modal, Button } from "./ui";
import { type PlanStats } from "@/lib/api";

function mb(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

export function ApplyModal({ open, onClose, stats, onConfirm }: {
  open: boolean;
  onClose: () => void;
  stats: PlanStats | undefined;
  onConfirm: () => void;
}) {
  if (!stats) return null;
  const total = stats.n_retag + stats.n_rename + stats.n_move + stats.n_delete;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Applicare il piano?"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Annulla</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>▶ Applica {total} operazioni</Button>
        </>
      }
    >
      <div className="flex flex-col gap-2 text-sm">
        <Row k="retag (tag corretti)" v={stats.n_retag} />
        <Row k="rinomina" v={stats.n_rename} />
        <Row k="sposta" v={stats.n_move} />
        <Row k="elimina (doppioni)" v={stats.n_delete} />
        <Row k="spazio liberato" v={`≈ ${mb(stats.space_freed_bytes)}`} />
        <div className="mt-2 border border-border px-3 py-2 text-xs text-ok">
          ✓ Tutto annullabile da HISTORY. Gli eliminati vanno in quarantena, non cancellati.
        </div>
      </div>
    </Modal>
  );
}

function Row({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className="tnum text-fg-strong">{v}</span>
    </div>
  );
}
