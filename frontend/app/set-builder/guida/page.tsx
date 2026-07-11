"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { useT } from "@/lib/i18n";

/* Guida del Set Builder: pagina statica, deterministica e onesta — descrive solo
   ciò che il sistema fa davvero, coi numeri veri del motore (pesi, soglie, curve). */

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

const STRATEGY_ROW_KEYS = ["smooth", "progressive", "contrast", "experimental", "peakTime", "warmUp", "closing"] as const;

export default function SetBuilderGuide() {
  const t = useT();
  const g = t.setBuilder.guide;

  const toc: { id: string; label: string }[] = [
    { id: "flusso", label: g.tocFlusso },
    { id: "controlli", label: g.tocControlli },
    { id: "motore", label: g.tocMotore },
    { id: "strategie", label: g.tocStrategie },
    { id: "score", label: g.tocScore },
    { id: "dati", label: g.tocDati },
    { id: "workbench", label: g.tocWorkbench },
    { id: "scorciatoie", label: g.tocScorciatoie },
  ];

  return (
    <PageLayout title={g.pageTitle} meta="SET BUILDER">
      <Link href="/set-builder" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Set Builder
      </Link>

      <nav aria-label={g.summaryAria} className="mb-6 flex flex-wrap gap-x-4 gap-y-1.5 border-y border-border py-3 text-xs">
        {toc.map((item) => (
          <a key={item.id} href={`#${item.id}`} className="text-muted transition-colors hover:text-fg">
            {item.label}
          </a>
        ))}
      </nav>

      <div className="space-y-6">
        <S id="flusso" title={g.tocFlusso}>
          <p>{g.flussoP1}</p>
        </S>

        <S id="controlli" title={g.tocControlli}>
          <p>
            <K>{g.controlliPlaylistTerm}</K>{" "}{g.controlliPlaylistRest}
          </p>
          <p>
            <K>{g.controlliDurataTerm}</K>{" "}{g.controlliDurataRest}
          </p>
          <p>
            <K>{g.controlliPresetTerm}</K>{" "}{g.controlliPresetRest}
          </p>
          <p>
            <K>{t.setBuilder.sectionEngine}</K>{" "}{g.controlliMotoreRest1}{" "}
            <K>{t.setBuilder.freePromptLabel}</K>{" "}{g.controlliMotoreRest2}
          </p>
          <p>
            <K>{t.setBuilder.advancedOptionsLabel}</K>{" "}{g.controlliAdvancedRest}
          </p>
        </S>

        <S id="motore" title={g.tocMotore}>
          <p>
            <K>{g.motoreAlgoTerm}</K>{" "}{g.motoreAlgoRest}
          </p>
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>
              {g.motoreStep1Prefix} <K>Candidate Engine</K>{" "}{g.motoreStep1Rest}
            </li>
            <li>
              {g.motoreStep2Prefix} <K>beam search</K>{" "}{g.motoreStep2Rest}
            </li>
            <li>
              {g.motoreStep3Prefix} <K>{g.transitionScoreTerm}</K>{" "}{g.motoreStep3Mid}{" "}
              <K>{g.genreCoherenceTerm}</K>{" "}{g.motoreStep3Suffix}
            </li>
          </ol>
          <p>
            <K>{g.genreCoherenceTermCap}</K>{" "}{g.motoreGenereRest1} <K>{g.genreFamiliesTerm}</K>{" "}
            {g.motoreGenereRest2}
          </p>
          <p>
            <K>AI</K>{" "}{g.motoreAiRest1} <K>{g.motore60CandidatesTerm}</K>{" "}
            {g.motoreAiRest2} <K>{g.motoreReverifiedTerm}</K>{" "}
            {g.motoreAiRest3} <K>{t.setBuilder.technicalLabel}</K>{" "}{g.motoreAiRest4}{" "}
            <K>{t.setBuilder.creativeLabel}</K>{" "}{g.motoreAiRest5}
          </p>
        </S>

        <S id="strategie" title={g.tocStrategie}>
          <p>
            {g.strategieP1Prefix} <K>{g.characterTerm}</K>{" "}{g.strategieP1Rest}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>{g.strategyTable.headers.strategy}</th>
                  <th className={TH}>{g.strategyTable.headers.curve}</th>
                  <th className={TH}>{g.strategyTable.headers.energy}</th>
                  <th className={TH}>{g.strategyTable.headers.jumps}</th>
                  <th className={TH}>{g.strategyTable.headers.character}</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                {STRATEGY_ROW_KEYS.map((key) => {
                  const row = g.strategyTable.rows[key];
                  return (
                    <tr key={key}>
                      <td className={TD}>{row.name}</td>
                      <td className={TD}>{row.curve}</td>
                      <td className={`${TD} tnum`}>{row.energy}</td>
                      <td className={TD}>{row.jumps}</td>
                      <td className={TD}>{row.character}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">{g.strategieFootnote}</p>
        </S>

        <S id="score" title={g.tocScore}>
          <p>
            {g.scoreP1Prefix} <K>{g.score0to100Term}</K>{g.scoreP1Suffix}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>{g.scoreWeightTable.headers.component}</th>
                  <th className={TH}>{g.scoreWeightTable.headers.weight}</th>
                  <th className={TH}>{g.scoreWeightTable.headers.assessment}</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                <tr>
                  <td className={TD}>{g.scoreWeightTable.rows.bpm.name}</td>
                  <td className={`${TD} tnum`}>{g.scoreWeightTable.rows.bpm.weight}</td>
                  <td className={TD}>{g.scoreWeightTable.rows.bpm.desc}</td>
                </tr>
                <tr>
                  <td className={TD}>{g.scoreWeightTable.rows.key.name}</td>
                  <td className={`${TD} tnum`}>{g.scoreWeightTable.rows.key.weight}</td>
                  <td className={TD}>{g.scoreWeightTable.rows.key.desc}</td>
                </tr>
                <tr>
                  <td className={TD}>{g.scoreWeightTable.rows.duration.name}</td>
                  <td className={`${TD} tnum`}>{g.scoreWeightTable.rows.duration.weight}</td>
                  <td className={TD}>{g.scoreWeightTable.rows.duration.desc}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>{g.scoreP2Prefix} <K>{g.transitionClassesTerm}</K>:</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className={TH}>{g.transitionClassTable.headers.class}</th>
                  <th className={TH}>{g.transitionClassTable.headers.when}</th>
                  <th className={TH}>{g.transitionClassTable.headers.forDj}</th>
                </tr>
              </thead>
              <tbody className="text-fg">
                <tr>
                  <td className={TD}>{g.transitionClassTable.rows.safe.name}</td>
                  <td className={TD}>{g.transitionClassTable.rows.safe.whenPrefix} <em>{g.transitionClassTable.rows.safe.whenEm}</em> {g.transitionClassTable.rows.safe.whenSuffix}</td>
                  <td className={TD}>{g.transitionClassTable.rows.safe.forDj}</td>
                </tr>
                <tr>
                  <td className={TD}>{g.transitionClassTable.rows.reset.name}</td>
                  <td className={TD}>{g.transitionClassTable.rows.reset.when}</td>
                  <td className={TD}>{g.transitionClassTable.rows.reset.forDj}</td>
                </tr>
                <tr>
                  <td className={TD}>{g.transitionClassTable.rows.risk.name}</td>
                  <td className={TD}>{g.transitionClassTable.rows.risk.when}</td>
                  <td className={TD}>{g.transitionClassTable.rows.risk.forDj}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">{g.scoreFootnote}</p>
        </S>

        <S id="dati" title={g.tocDati}>
          <p>
            <K>{g.datiBpmKeyTerm}</K>{" "}{g.datiBpmKeyRest}
          </p>
          <p>
            <K>{g.datiEnergyTerm}</K>{" "}{g.datiEnergyRest}
          </p>
          <p>
            <K>{g.datiGenreTerm}</K>{" "}{g.datiGenreRest}
          </p>
        </S>

        <S id="workbench" title={g.tocWorkbench}>
          <p>{g.workbenchP1}</p>
          <ul className="list-disc space-y-1.5 pl-5">
            <li><K>{g.setArcTermLower}</K>{" "}{g.workbenchArcRest}</li>
            <li><K>{g.mixTipTerm}</K>{" "}{g.workbenchTipMid} <K>{g.workbenchCriticalPointsTerm}</K>{" "}{g.workbenchTipSuffix}</li>
            <li><K>{g.reorderTerm}</K>{" "}{g.workbenchReorderRest}</li>
            <li><K>{g.alternativesPerPositionTerm}</K>{" "}{g.workbenchAltRest}</li>
            <li><K>export</K>{" "}{g.workbenchExportRest}</li>
          </ul>
        </S>

        <S id="scorciatoie" title={g.tocScorciatoie}>
          <p>
            <kbd className="rounded-none border border-border px-1 text-xs">⌘⏎</kbd>{" "}{g.scorciatoieRest}
          </p>
        </S>
      </div>
    </PageLayout>
  );
}
