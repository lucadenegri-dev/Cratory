"use client";

/* Lo stato dell'aggiornamento, in un posto solo.
 *
 * Fuori dal guscio desktop non fa nulla e non chiede nulla: nel browser non
 * c'è niente da installare. Dentro, controlla una volta per lancio e fallisce
 * in silenzio — un problema di rete all'avvio non è una notizia da dare a chi
 * non ha chiesto niente. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { isDesktopShell } from "@/lib/external-url";
import {
  ascoltaInstallazione,
  ascoltaProgresso,
  controlla,
  erroreDi,
  installa,
  riavvia,
  type ErroreAggiornamento,
  type InfoAggiornamento,
} from "@/lib/updates-bridge";

export type StatoAggiornamento =
  | { fase: "sconosciuto" }
  | { fase: "aggiornato" }
  | { fase: "disponibile"; info: InfoAggiornamento }
  | { fase: "non_verificabile"; errore: ErroreAggiornamento }
  | { fase: "scaricando"; info: InfoAggiornamento; scaricati: number; totale: number | null }
  | { fase: "installando"; info: InfoAggiornamento }
  | { fase: "fallito"; info: InfoAggiornamento | null; errore: ErroreAggiornamento };

type Contesto = {
  stato: StatoAggiornamento;
  /** Solo qui c'è qualcosa da installare. */
  nelGuscio: boolean;
  controllaOra: () => Promise<void>;
  installaOra: () => Promise<void>;
  riavviaOra: () => Promise<void>;
};

const ContestoAggiornamento = createContext<Contesto>({
  stato: { fase: "sconosciuto" },
  nelGuscio: false,
  controllaOra: async () => {},
  installaOra: async () => {},
  riavviaOra: async () => {},
});

export function useAggiornamento(): Contesto {
  return useContext(ContestoAggiornamento);
}

/* Girare dentro il guscio non e' uno stato che cambia: e' un fatto
   sull'ambiente, che pero' il server non puo' conoscere. useSyncExternalStore
   e' il modo di leggerlo senza far divergere l'idratazione e senza chiamare
   setState dentro un effetto: niente sottoscrizione (non cambia mai), false
   sul server, la verita' sul client. */
const NESSUNA_SOTTOSCRIZIONE = () => () => {};
const nelGuscioSulServer = () => false;

export function AggiornamentoProvider({ children }: { children: ReactNode }) {
  const [stato, setStato] = useState<StatoAggiornamento>({ fase: "sconosciuto" });
  const nelGuscio = useSyncExternalStore(NESSUNA_SOTTOSCRIZIONE, isDesktopShell, nelGuscioSulServer);
  // Lo stato serve anche a chi non sta rendendo (installaOra): leggerlo da
  // dentro un updater di setStato per portarselo fuori renderebbe impuro
  // l'updater, che React ha il diritto di eseguire due volte.
  const rifStato = useRef<StatoAggiornamento>({ fase: "sconosciuto" });
  useEffect(() => {
    rifStato.current = stato;
  }, [stato]);

  /* I tre esiti si calcolano qui, senza toccare lo stato di React: chi chiama
     decide se e quando applicarli. Serve al controllo all'avvio (che non deve
     scrivere su un componente gia' smontato) e tiene la regola dei tre esiti
     in un posto solo invece che duplicata fra effetto e bottone. */
  const calcolaStato = useCallback(async (): Promise<StatoAggiornamento> => {
    try {
      const info = await controlla();
      return info ? { fase: "disponibile", info } : { fase: "aggiornato" };
    } catch (e) {
      return { fase: "non_verificabile", errore: erroreDi(e) };
    }
  }, []);

  const controllaOra = useCallback(async () => {
    setStato(await calcolaStato());
  }, [calcolaStato]);

  useEffect(() => {
    if (!nelGuscio) return;
    let vivo = true;
    void calcolaStato().then((s) => {
      if (vivo) setStato(s);
    });
    return () => {
      vivo = false;
    };
  }, [nelGuscio, calcolaStato]);

  const installaOra = useCallback(async () => {
    const attuale = rifStato.current;
    if (attuale.fase !== "disponibile") return;
    const info: InfoAggiornamento = attuale.info;
    setStato({ fase: "scaricando", info, scaricati: 0, totale: null });
    const smetti: Array<() => void> = [];
    try {
      smetti.push(
        await ascoltaProgresso((p) =>
          setStato((s) =>
            s.fase === "scaricando" ? { ...s, scaricati: p.scaricati, totale: p.totale } : s,
          ),
        ),
      );
      smetti.push(
        await ascoltaInstallazione(() =>
          setStato((s) => (s.fase === "scaricando" ? { fase: "installando", info: s.info } : s)),
        ),
      );
      await installa();
      // Se la promessa si risolve, l'app non si è riavviata: l'installazione è
      // comunque avvenuta, e il riavvio resta da fare.
      setStato((s) =>
        s.fase === "scaricando" || s.fase === "installando" ? { fase: "installando", info: s.info } : s,
      );
    } catch (e) {
      setStato({ fase: "fallito", info, errore: erroreDi(e) });
    } finally {
      smetti.forEach((f) => f());
    }
  }, []);

  const riavviaOra = useCallback(async () => {
    await riavvia();
  }, []);

  const valore = useMemo(
    () => ({ stato, nelGuscio, controllaOra, installaOra, riavviaOra }),
    [stato, nelGuscio, controllaOra, installaOra, riavviaOra],
  );

  return <ContestoAggiornamento.Provider value={valore}>{children}</ContestoAggiornamento.Provider>;
}
