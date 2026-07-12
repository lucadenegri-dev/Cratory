"use client";

// ConfirmModal: sostituto design-system di window.confirm. Costruito sopra
// Modal (che gestisce già Escape, focus e role="dialog"): titolo, messaggio,
// Annulla (ghost) + azione di conferma. tone="danger" per le azioni
// distruttive (eliminazioni, sovrascritture irreversibili).
// onConfirm NON chiude da solo: il chiamante azzera il proprio stato
// (stessa convenzione del modal di eliminazione in /sets/[id]).

import { Button, Modal } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ReactNode } from "react";

export function ConfirmModal({
  open, title, message, confirmLabel, tone = "default", onConfirm, onClose,
}: {
  open: boolean;
  title?: ReactNode;
  message: ReactNode;
  confirmLabel?: ReactNode;
  tone?: "danger" | "default";
  onConfirm: () => void;
  onClose: () => void;
}) {
  const t = useT();
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title ?? t.common.confirm}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>{t.common.cancel}</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} size="sm" onClick={onConfirm}>
            {confirmLabel ?? t.common.confirm}
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted">{message}</p>
    </Modal>
  );
}
