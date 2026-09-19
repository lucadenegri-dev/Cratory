"use client";

import { useEffect, useState } from "react";
import { type ManualTransition } from "@/lib/api";
import { Textarea } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Props = {
  transition: ManualTransition;
  variant: "in" | "out";
  onSaveNote: (transition: ManualTransition, note: string) => void;
};

/** Il passaggio fra due tracce vicine: quanto pitch serve, che rapporto hanno
 *  le tonalità, e l'appunto — che è legato alle due TRACCE, non alle due righe.
 *  Dove un dato manca si legge «sconosciuto»: mai un punteggio al suo posto,
 *  che sembrerebbe un giudizio e non lo sarebbe. */
export function TransitionPanel({ transition: tr, variant, onSaveNote }: Props) {
  const t = useT();
  const [draft, setDraft] = useState(tr.note ?? "");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- riallineo il draft al passaggio mostrato, come fa il dettaglio con l'appunto di riga
    setDraft(tr.note ?? "");
  }, [tr.from_track_id, tr.to_track_id, tr.note]);

  const ignoto = t.sets.manual.unknownValue;
  const pitch = tr.bpm_percent === null
    ? ignoto
    : `${tr.bpm_percent > 0 ? "+" : ""}${tr.bpm_percent.toLocaleString("it-IT")} %`;

  return (
    <div data-testid={`transition-panel-${variant}`} className="border-t border-border pt-3">
      <div className="mb-1 text-xs uppercase tracking-wider text-muted">
        {variant === "in" ? t.sets.manual.transitionInTitle : t.sets.manual.transitionOutTitle}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="tnum">
          {tr.bpm_from ?? ignoto} → {tr.bpm_to ?? ignoto}
        </span>
        <span className="text-xs text-muted">
          {t.sets.manual.pitchLabel} <span className="tnum">{pitch}</span>
          {tr.halftime && <>{" "}· {t.sets.manual.halftimeLabel}</>}
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-sm">
        <span>{tr.key_from ?? ignoto} → {tr.key_to ?? ignoto}</span>
        {tr.score !== null && <span className="tnum text-xs text-muted">{tr.score}/100</span>}
      </div>
      <Textarea className="mt-2" value={draft} rows={2}
        placeholder={t.sets.manual.transitionNotePlaceholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => { if (draft.trim() !== (tr.note ?? "")) onSaveNote(tr, draft); }} />
    </div>
  );
}
