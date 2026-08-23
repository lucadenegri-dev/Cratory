"use client";

/* Il flusso di aggiornamento dentro il guscio desktop: qui c'è qualcosa da
   installare, e questo componente è l'unico posto che lo fa fare. La versione
   in uso arriva come prop perché la legge VersionCard, una volta sola, per
   entrambi i modi. */

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui";
import { ConfirmModal } from "@/components/confirm-modal";
import { useT, type Dictionary } from "@/lib/i18n";
import { useAggiornamento } from "@/lib/updates";

const MB = 1_000_000;
const mb = (byte: number) => Math.round(byte / MB).toString();

/** La frase la sceglie il dizionario a partire dal codice di fase: il guscio
 *  manda il codice, non la prosa. */
function frase(t: Dictionary, codice: string): string {
  switch (codice) {
    case "permessi": return t.settings.versionErrPermessi;
    case "controllo": return t.settings.versionErrControllo;
    case "scaricamento": return t.settings.versionErrScaricamento;
    case "installazione": return t.settings.versionErrInstallazione;
    default: return t.settings.versionErrSconosciuto;
  }
}

export function AggiornamentoGuscio({ versione }: { versione: string }) {
  const t = useT();
  const { stato, controllaOra, installaOra, riavviaOra } = useAggiornamento();
  const [conferma, setConferma] = useState(false);
  // Durante download e installazione non si ricontrolla: il controllo
  // sostituirebbe lo stato da cui dipende ciò che sta già succedendo.
  const occupato = stato.fase === "scaricando" || stato.fase === "installando";

  const corpo = () => {
    switch (stato.fase) {
      case "aggiornato":
        return <p className="mt-3 text-xs text-muted">{t.settings.versionUpToDate}</p>;

      case "non_verificabile":
        return (
          <p className="mt-3 text-xs text-danger">
            {frase(t, stato.errore.codice)}{" "}
            <span className="text-faint">{stato.errore.dettaglio}</span>
          </p>
        );

      case "scaricando":
        return (
          <p className="tnum mt-3 text-xs text-muted">
            {stato.totale
              ? t.settings.versionDownloading(mb(stato.scaricati), mb(stato.totale))
              : t.settings.versionDownloadingUnknown(mb(stato.scaricati))}
          </p>
        );

      case "installando":
        return <p className="mt-3 text-xs text-muted">{t.settings.versionInstalling}</p>;

      case "fallito":
        return (
          <div className="mt-3 border-t border-border pt-3">
            <p className="text-xs text-danger">{frase(t, stato.errore.codice)}</p>
            <p className="mt-1 text-[10px] text-faint">{stato.errore.dettaglio}</p>
            {/* A questo punto il backend è già stato terminato: senza un
                riavvio l'app resta un guscio vuoto. */}
            <Button className="mt-2" size="sm" variant="outline" onClick={() => void riavviaOra()}>
              {t.settings.versionRestart}
            </Button>
          </div>
        );

      case "disponibile":
        return (
          <div className="mt-3 border-t border-border pt-3">
            <p className="text-sm text-fg-strong">{t.settings.versionAvailable(stato.info.versione)}</p>
            {stato.info.note && (
              <>
                <p className="mt-2 text-[10px] uppercase tracking-wider text-faint">
                  {t.settings.versionNotesHeading}
                </p>
                {/* Testo di GitHub, non nostro: si mostra come citazione. */}
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap border-l-2 border-border pl-3 text-xs text-muted">
                  {stato.info.note}
                </pre>
              </>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="primary" onClick={() => setConferma(true)}>
                {t.settings.versionInstall}
              </Button>
              {/* La via d'uscita quando l'automatismo non funziona. */}
              <a
                href={`https://github.com/lucadenegri-dev/Cratory/releases/tag/v${stato.info.versione}`}
                target="_blank"
                rel="noreferrer"
              >
                <Button size="sm" variant="outline">
                  <ExternalLink size={14} /> {t.settings.versionOpenRelease}
                </Button>
              </a>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-fg">{versione}</span>
        <Button size="sm" variant="outline" disabled={occupato} onClick={() => void controllaOra()}>
          {t.settings.versionCheck}
        </Button>
      </div>
      {corpo()}
      <ConfirmModal
        open={conferma}
        title={t.settings.versionConfirmTitle}
        message={t.settings.versionConfirmBody}
        confirmLabel={t.settings.versionInstall}
        onClose={() => setConferma(false)}
        onConfirm={() => {
          setConferma(false);
          void installaOra();
        }}
      />
    </>
  );
}
