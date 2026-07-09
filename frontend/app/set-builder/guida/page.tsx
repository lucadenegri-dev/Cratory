"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageLayout } from "@/components/page-layout";

/* Guida del Set Builder: pagina statica, deterministica e onesta — descrive solo
   ciò che il sistema fa davvero, coi numeri veri del motore (pesi, soglie, curve). */

const TOC = [
  { id: "flusso", label: "Il flusso di lavoro" },
  { id: "controlli", label: "I controlli" },
  { id: "motore", label: "Come ragiona il motore" },
  { id: "strategie", label: "Le sette strategie" },
  { id: "score", label: "Lo score di transizione" },
  { id: "dati", label: "Da dove vengono i dati" },
  { id: "workbench", label: "Il workbench" },
  { id: "scorciatoie", label: "Scorciatoie" },
];

function S({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-border pt-6 first:border-t-0 first:pt-0">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg-strong">{title}</h2>
      <div className="max-w-[68ch] space-y-3 text-sm leading-relaxed text-fg">{children}</div>
    </section>
  );
}

function K({ children }: { children: React.ReactNode }) {
  return <span className="font-medium text-fg-strong">{children}</span>;
}

const TH = "border-b border-border-strong px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted";
const TD = "border-b border-border px-3 py-2 align-top";

export default function SetBuilderGuide() {
  return (
    <PageLayout title="Guida" meta="SET BUILDER">
      <Link href="/set-builder" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Set Builder
      </Link>

      <nav aria-label="Sommario" className="mb-6 flex flex-wrap gap-x-4 gap-y-1.5 border-y border-border py-3 text-xs">
        {TOC.map((t) => (
          <a key={t.id} href={`#${t.id}`} className="text-muted transition-colors hover:text-fg">
            {t.label}
          </a>
        ))}
      </nav>

      <div className="space-y-6">
        <S id="flusso" title="Il flusso di lavoro">
          <p>
            Brief → generazione → workbench: se il risultato non convince, di solito è più
            rapido correggerlo nel workbench (una sostituzione, un riordino) che rigenerare
            tutto da capo.
          </p>
        </S>

        <S id="controlli" title="I controlli">
          <p>
            <K>Playlist di partenza</K>{" "}— il set nasce solo dalle tracce di quella playlist;
            vuoto = tutta la libreria. Servono comunque BPM e tonalità (da Rekordbox): una
            traccia senza BPM non è mai candidata.
          </p>
          <p>
            <K>Durata</K>{" "}— il motore riempie il tempo richiesto e si ferma appena lo supera.
          </p>
          <p>
            <K>Preset rapidi</K>{" "}— impostano in un colpo strategia, durata e arco BPM/energia.
            Appena modifichi a mano uno di quei campi, il preset si disattiva: non c&apos;è mai
            uno stato nascosto.
          </p>
          <p>
            <K>Motore</K>{" "}— Algoritmo (default) o AI: vedi sotto. Con l&apos;AI compare il{" "}
            <K>prompt libero</K>{" "}e lo stile Tecnico/Creativo; in Algoritmo il prompt non
            esiste perché il motore deterministico non lo legge.
          </p>
          <p>
            <K>Opzioni avanzate</K>{" "}— l&apos;arco del set (BPM ed energia da→a), la strategia,
            i generi (match esatto sui tag, vuoto = tutti; se il filtro svuota il pool te lo
            dice l&apos;errore), max tracce per artista, artisti seed (spinta forte in
            selezione, non una garanzia), «evita tracce corte» (&lt; 2 minuti fuori), «solo
            brani posseduti» (default disk-first: il set che esce è suonabile, file alla mano).
          </p>
        </S>

        <S id="motore" title="Come ragiona il motore">
          <p>
            <K>Algoritmo</K>{" "}— deterministico e spiegabile: stesso input, stesso set. Lavora in
            tre passi:
          </p>
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>
              Il <K>Candidate Engine</K>{" "}filtra la libreria sui tuoi vincoli: possesso,
              finestra BPM attorno all&apos;arco (±12), durata minima, generi, sorgenti. I
              duplicati (stesso brano in grafie diverse) vengono collassati — vince la copia
              posseduta.
            </li>
            <li>
              Una <K>beam search</K>{" "}costruisce più scalette in parallelo invece di scegliere
              avidamente traccia per traccia: conserva le tracce «ponte» che servono più
              avanti nell&apos;arco e alla fine tiene la scaletta col punteggio complessivo
              migliore (mai peggiore della scelta greedy).
            </li>
            <li>
              Ogni passo è guidato dallo <K>score di transizione</K>{" "}(sotto), dall&apos;aderenza
              alla traiettoria BPM, dall&apos;arco di energia e dal carattere della strategia.
            </li>
          </ol>
          <p>
            <K>AI</K>{" "}— interpreta il prompt («parti morbido e atmosferico, poi vira club…»).
            Non vede mai l&apos;intera libreria: riceve al massimo <K>60 candidate</K>{" "}già
            filtrate dagli stessi vincoli, con un profilo sintetico della palette (range BPM,
            chiavi prevalenti, generi). Ogni sua scelta viene <K>riverificata</K>{" "}dal motore
            deterministico: score ricalcolati, duplicati e vincoli imposti, warning espliciti.
            L&apos;AI non può inventare tracce né dati tecnici. <K>Tecnico</K>{" "}= mix prudente
            sui soli dati; <K>Creativo</K>{" "}= arco emotivo, contrasti voluti e sorprese, coi
            rischi segnalati.
          </p>
        </S>

        <S id="strategie" title="Le sette strategie">
          <p>
            La strategia dà il <K>carattere</K>{" "}del set: curva BPM, arco di energia imposto
            (quando non ne chiedi uno tu), tolleranza ai salti bruschi e premi ai reset.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>Strategia</th>
                  <th className={TH}>Curva BPM</th>
                  <th className={TH}>Energia imposta</th>
                  <th className={TH}>Salti bruschi</th>
                  <th className={TH}>Carattere</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                <tr><td className={TD}>Fluido</td><td className={TD}>lineare</td><td className={`${TD} tnum`}>—</td><td className={TD}>penalizzati</td><td className={TD}>transizioni morbide, rischio minimo</td></tr>
                <tr><td className={TD}>Progressivo</td><td className={TD}>lineare</td><td className={`${TD} tnum`}>35 → 85</td><td className={TD}>penalizzati</td><td className={TD}>energia in salita costante</td></tr>
                <tr><td className={TD}>Contrasti</td><td className={TD}>lineare</td><td className={`${TD} tnum`}>—</td><td className={TD}>ammessi</td><td className={TD}>2-3 stacchi deliberati a ⅓ e ⅔ del set</td></tr>
                <tr><td className={TD}>Sperimentale</td><td className={TD}>lineare</td><td className={`${TD} tnum`}>—</td><td className={TD}>ammessi</td><td className={TD}>premia cambi di tonalità e genere</td></tr>
                <tr><td className={TD}>Peak time</td><td className={TD}>sale in fretta</td><td className={`${TD} tnum`}>70 → 92</td><td className={TD}>penalizzati</td><td className={TD}>dritto al clou, resta alto</td></tr>
                <tr><td className={TD}>Warm-up</td><td className={TD}>sale piano</td><td className={`${TD} tnum`}>25 → 55</td><td className={TD}>penalizzati</td><td className={TD}>apre la serata, resta basso</td></tr>
                <tr><td className={TD}>Chiusura</td><td className={TD}>lineare</td><td className={`${TD} tnum`}>75 → 40</td><td className={TD}>penalizzati</td><td className={TD}>scende nel finale, reset premiato in coda</td></tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">
            L&apos;energia che imposti a mano vince sempre su quella della strategia.
          </p>
        </S>

        <S id="score" title="Lo score di transizione">
          <p>
            Ogni passaggio tra due tracce ha uno <K>score 0–100</K>, composto così:
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>Componente</th>
                  <th className={TH}>Peso</th>
                  <th className={TH}>Come viene valutata</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                <tr>
                  <td className={TD}>BPM</td>
                  <td className={`${TD} tnum`}>max 50</td>
                  <td className={TD}>Δ ≤ 2 ottimo · ≤ 5 buono · ≤ 8 rischioso · oltre, difficile. Riconosce il mezzo/doppio tempo (140 ↔ 70 è mixabile).</td>
                </tr>
                <tr>
                  <td className={TD}>Tonalità</td>
                  <td className={`${TD} tnum`}>max 40</td>
                  <td className={TD}>Camelot graduata sulla distanza della ruota: stessa key &gt; adiacente/relativa &gt; +2 «energy boost» &gt; diagonale &gt; tritono.</td>
                </tr>
                <tr>
                  <td className={TD}>Durata</td>
                  <td className={`${TD} tnum`}>max 10</td>
                  <td className={TD}>Penalizza solo le tracce molto corte (&lt; 90s).</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>Dallo score (e dai dati di energia/genere) nascono le tre <K>classi di transizione</K>:</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>Classe</th>
                  <th className={TH}>Quando</th>
                  <th className={TH}>Per il DJ</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                <tr><td className={TD}>Tecnicamente sicura</td><td className={TD}>score ≥ 70 <em>e</em> chiave compatibile</td><td className={TD}>beatmatch e blend, mix tranquillo</td></tr>
                <tr><td className={TD}>Reset voluto</td><td className={TD}>calo di energia ≥ 15 o cambio di genere</td><td className={TD}>stacco netto per resettare la pista</td></tr>
                <tr><td className={TD}>Azzardo creativo</td><td className={TD}>tutto il resto (anche BPM facile ma key in contrasto)</td><td className={TD}>mix breve, maschera con l&apos;EQ</td></tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">
            Gli stessi score e classi guidano anche la pagina Transizioni e le alternative del
            workbench: un solo linguaggio, deterministico, mai inventato.
          </p>
        </S>

        <S id="dati" title="Da dove vengono i dati">
          <p>
            <K>BPM e tonalità</K>{" "}— da Rekordbox (import XML della collezione). Cratory non li
            stima né li inventa mai: se mancano, la traccia resta fuori dalle candidate.
          </p>
          <p>
            <K>Energia (0–100)</K>{" "}— misurata dai tuoi file audio: volume percepito,
            brillantezza e densità ritmica su tre finestre del brano (inizio, centro, fine),
            calibrata sui percentili della tua libreria. Non è il BPM travestito: a parità di
            tempo distingue la traccia ariosa da quella che picchia. Per i lead senza file
            resta una stima da BPM+genere.
          </p>
          <p>
            <K>Genere, label, tag</K>{" "}— li cura Sortory; Cratory li legge dai file durante
            l&apos;indicizzazione e non li modifica mai.
          </p>
        </S>

        <S id="workbench" title="Il workbench">
          <p>Il set generato si apre nel dettaglio, dove trovi:</p>
          <ul className="list-disc space-y-1.5 pl-5">
            <li>l&apos;<K>arco del set</K>{" "}disegnato sopra la scaletta (linea BPM + area energia);</li>
            <li>un <K>consiglio di mix</K>{" "}per ogni transizione (deterministico, dai dati) e i <K>punti critici</K>{" "}da preparare;</li>
            <li>il <K>riordino</K>{" "}con le frecce (ottimistico: la UI risponde subito, il server ricalcola gli score);</li>
            <li>le <K>alternative per posizione</K>{" "}— cinque lenti: più sicura, più morbida, più dura, stesso artista, sorprendente — con lo score verso il brano prima e dopo;</li>
            <li>l&apos;<K>export</K>{" "}in TXT/CSV/Markdown o la creazione di una playlist Spotify.</li>
          </ul>
        </S>

        <S id="scorciatoie" title="Scorciatoie">
          <p>
            <kbd className="rounded-none border border-border px-1 text-xs">⌘⏎</kbd>{" "}(o
            Ctrl+Invio) genera da qualsiasi campo del form. Da una playlist, «Costruisci set»
            arriva qui con la playlist già selezionata.
          </p>
        </S>
      </div>
    </PageLayout>
  );
}
