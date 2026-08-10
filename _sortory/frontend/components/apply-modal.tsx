"use client";

import { Modal, Button } from "./ui";
import { type PlanStats } from "@/lib/api";
import { useT } from "@/lib/i18n";

function mb(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

export function ApplyModal({ open, onClose, stats, onConfirm }: {
  open: boolean;
  onClose: () => void;
  stats: PlanStats | undefined;
  onConfirm: () => void;
}) {
  const t = useT();
  if (!stats) return null;
  const total = stats.n_retag + stats.n_rename + stats.n_move + stats.n_delete;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.plan.modalTitle}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>{t.common.cancel}</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>{t.plan.modalApplyBtn(total)}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-2 text-sm">
        <Row k={t.plan.modalRetag} v={stats.n_retag} />
        <Row k={t.plan.modalRename} v={stats.n_rename} />
        <Row k={t.plan.modalMove} v={stats.n_move} />
        <Row k={t.plan.modalDelete} v={stats.n_delete} />
        <Row k={t.plan.modalSpaceFreed} v={`≈ ${mb(stats.space_freed_bytes)}`} />
        <div className="mt-2 border border-border px-3 py-2 text-xs text-ok">
          {t.plan.modalHint}
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
