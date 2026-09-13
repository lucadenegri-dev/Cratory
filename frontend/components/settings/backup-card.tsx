"use client";

/* La scheda «Dati»: backup in uno zip (salva con nome quando il picker c'è,
   ~/Downloads altrimenti) e ripristino in due tempi — riepilogo, conferma,
   riavvio. Lo scambio dei file lo fa il backend al prossimo avvio, mai a caldo:
   nel guscio il riavvio parte da qui, nel browser si chiede di farlo a mano. */

import { useCallback, useEffect, useState } from "react";
import {
  cancelRestore, confirmRestore, createBackup, errText, fmtDate, getBackupEstimate,
  lastRestore, pickPath, prepareRestore,
  type BackupEstimate, type RestoreOutcome, type RestoreSummary,
} from "@/lib/api";
import { Alert, Button, Modal, Spinner } from "@/components/ui";
import { useAggiornamento } from "@/lib/updates";
import { useT, type Dictionary } from "@/lib/i18n";

const MB = 1_000_000;
const mb = (byte: number) => Math.max(1, Math.round(byte / MB)).toString();

// Gli errori del backend arrivano già tradotti dal client (dizionario
// `errors`): qui basta `errText(e)`.

function partiDellaStima(t: Dictionary, s: BackupEstimate): string {
  const parti: string[] = [];
  const v = (nome: string) => s.voci.find((x) => x.nome === nome);
  if (v("database")?.presente) parti.push(t.settings.backupPartDatabase);
  const covers = v("covers");
  if (covers?.presente && covers.byte > 0) parti.push(t.settings.backupPartCovers(1));
  if (v("env")?.presente || v("slskd")?.presente) parti.push(t.settings.backupPartCredentials);
  return parti.join(", ");
}

export function BackupCard() {
  const t = useT();
  const { nelGuscio, riavviaOra } = useAggiornamento();
  const [stima, setStima] = useState<BackupEstimate | null>(null);
  const [ultimo, setUltimo] = useState<RestoreOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [esito, setEsito] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [riepilogo, setRiepilogo] = useState<RestoreSummary | null>(null);
  const [riavvioManuale, setRiavvioManuale] = useState(false);

  const carica = useCallback(() => {
    getBackupEstimate().then(setStima).catch(() => setStima(null));
    lastRestore().then(setUltimo).catch(() => setUltimo(null));
  }, []);
  useEffect(carica, [carica]);

  const backupOra = async () => {
    setErrore(null);
    setEsito(null);
    setBusy(true);
    try {
      let path: string | null = null;
      if (stima?.picker_disponibile) {
        const r = await pickPath("save", undefined, t.settings.backupSavePrompt, stima.nome_di_default);
        if (!r.path) return;
        path = r.path;
      }
      const fatto = await createBackup(path);
      setEsito(t.settings.backupDone(fatto.percorso, mb(fatto.byte)));
      carica();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const ripristinaDa = async () => {
    setErrore(null);
    setEsito(null);
    setBusy(true);
    try {
      const r = await pickPath("file", undefined, t.settings.restorePickPrompt);
      if (!r.path) return;
      setRiepilogo(await prepareRestore(r.path));
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const annulla = () => {
    setRiepilogo(null);
    setRiavvioManuale(false);
    void cancelRestore().catch(() => undefined);
  };

  const conferma = async () => {
    setBusy(true);
    try {
      await confirmRestore();
      if (nelGuscio) {
        await riavviaOra();
      } else {
        setRiavvioManuale(true);
      }
    } catch (e) {
      setRiepilogo(null);
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-fg">
            {stima?.last_backup_at ? t.settings.backupLast(fmtDate(stima.last_backup_at)) : t.settings.backupNever}
          </p>
          {stima && (
            <p className="mt-1 text-xs text-muted">{t.settings.backupEstimate(mb(stima.byte), partiDellaStima(t, stima))}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" disabled={busy || !stima} onClick={() => void backupOra()}>
            {busy ? <Spinner /> : t.settings.backupNow}
          </Button>
          {stima?.picker_disponibile && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void ripristinaDa()}>
              {t.settings.restoreButton}
            </Button>
          )}
        </div>
      </div>
      <p className="mt-3 text-[10px] text-faint">{t.settings.backupNote}</p>
      {ultimo && (
        <p className="mt-2 text-xs text-muted">
          {ultimo.stato === "ok"
            ? t.settings.restoreApplied(fmtDate(ultimo.applicato_il), fmtDate(ultimo.backup_creato_il))
            : t.settings.restoreFailedLast}
        </p>
      )}
      {esito && <div className="mt-3"><Alert tone="success">{esito}</Alert></div>}
      {errore && <div className="mt-3"><Alert tone="danger">{errore}</Alert></div>}

      <Modal
        open={riepilogo !== null}
        onClose={annulla}
        title={t.settings.restoreTitle}
        footer={
          riavvioManuale ? null : (
            <>
              <Button variant="ghost" size="sm" onClick={annulla}>{t.common.cancel}</Button>
              <Button variant="danger" size="sm" disabled={busy} onClick={() => void conferma()}>
                {t.settings.restoreConfirm}
              </Button>
            </>
          )
        }
      >
        {riepilogo && (
          <div className="space-y-2 text-sm text-muted">
            <p className="text-fg">
              {t.settings.restoreSummary(fmtDate(riepilogo.creato_il), riepilogo.app_version ?? "—")}{" "}
              {t.settings.restoreCounts(riepilogo.tracce, riepilogo.playlist)}
            </p>
            <p>{riepilogo.ha_credenziali ? t.settings.restoreHasCredentials : t.settings.restoreNoCredentials}</p>
            <p>{t.settings.restoreWarnKept}</p>
            <p>{t.settings.restoreWarnQueue}</p>
            {riavvioManuale && <Alert tone="info">{t.settings.restoreManualRestart}</Alert>}
          </div>
        )}
      </Modal>
    </div>
  );
}
