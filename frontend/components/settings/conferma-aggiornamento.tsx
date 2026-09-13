"use client";

/* La conferma dell'aggiornamento, con il backup offerto prima. La stima
   arriva dal backend, che a questo punto è ancora vivo; se non risponde la
   domanda non compare e restano le due uscite di sempre. Il backup annullato
   o fallito NON fa partire l'installazione: l'utente ha detto di volerlo. */

import { useEffect, useState } from "react";
import { createBackup, errText, getBackupEstimate, pickPath, type BackupEstimate } from "@/lib/api";
import { Button, Modal } from "@/components/ui";
import { useT } from "@/lib/i18n";

const MB = 1_000_000;
const mb = (byte: number) => Math.max(1, Math.round(byte / MB)).toString();

export function ConfermaAggiornamento({ open, onClose, onInstall }: {
  open: boolean;
  onClose: () => void;
  onInstall: () => void;
}) {
  const t = useT();
  const [stima, setStima] = useState<BackupEstimate | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let vivo = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- riparte da zero a ogni apertura: il backend (external system) è la fonte della nuova stima
    setErrore(null);
    getBackupEstimate()
      .then((s) => { if (vivo) setStima(s); })
      .catch(() => { if (vivo) setStima(null); });
    return () => { vivo = false; };
  }, [open]);

  const backupPoiInstalla = async () => {
    if (!stima) return;
    setErrore(null);
    setInCorso(true);
    try {
      let path: string | null = null;
      if (stima.picker_disponibile) {
        const r = await pickPath("save", undefined, t.settings.backupSavePrompt, stima.nome_di_default);
        if (!r.path) return; // annullato: si resta sulla modale
        path = r.path;
      }
      await createBackup(path);
      onInstall();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={inCorso ? () => undefined : onClose}
      title={t.settings.versionConfirmTitle}
      footer={
        <>
          <Button variant="ghost" size="sm" disabled={inCorso} onClick={onClose}>{t.common.cancel}</Button>
          {stima ? (
            <>
              <Button variant="outline" size="sm" disabled={inCorso} onClick={onInstall}>
                {t.settings.versionInstallWithoutBackup}
              </Button>
              <Button variant="primary" size="sm" disabled={inCorso} onClick={() => void backupPoiInstalla()}>
                {t.settings.versionBackupAndInstall}
              </Button>
            </>
          ) : (
            <Button variant="primary" size="sm" onClick={onInstall}>{t.settings.versionInstall}</Button>
          )}
        </>
      }
    >
      <p className="text-sm text-muted">{t.settings.versionConfirmBody}</p>
      {stima && <p className="mt-2 text-sm text-fg">{t.settings.versionBackupQuestion(mb(stima.byte))}</p>}
      {inCorso && <p className="mt-2 text-xs text-muted">{t.settings.versionBackupRunning}</p>}
      {errore && (
        <p className="mt-2 text-xs text-danger">
          {t.settings.versionBackupFailed} <span className="text-faint">{errore}</span>
        </p>
      )}
    </Modal>
  );
}
