/**
 * Logica pura della pagina ISSUES: cosa si può accettare e come, e l'ordine
 * stabile dei gruppi. Nessun React, nessuna rete: testabile a secco.
 */
import type { Issue } from "@/lib/organize/api";

export type GroupBy = "type" | "severity" | "none";

// Stessi campi retaggabili del backend (planner.EDITABLE_TAG_FIELDS).
export const RETAGGABLE = new Set([
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
]);

const SEV_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

// Un'issue è "fixable" se ha un'azione applicabile: quarantena, svuotamento,
// o un campo retaggabile. Stessa logica usata nella riga (vedi IssueRow).
export function issueIsFixable(i: Issue): boolean {
  const action = i.suggested_fix_json?.action;
  if (action === "clear" || action === "quarantine") return true;
  return i.field != null && RETAGGABLE.has(i.field);
}

// Override "forte" (match sicuro da provider): la ConfBadge mappa high→strong.
// Riservato alle proposte di origine provider: le proposte AI (genre_review)
// sono per definizione "da rivedere", mai accettabili in blocco come un match
// sicuro — anche quando portano confidence "high" nel vocabolario dell'AI.
export function issueIsStrong(i: Issue): boolean {
  if (i.suggested_fix_json?.source !== "provider") return false;
  const c = i.suggested_fix_json?.confidence;
  return c === "high" || c === "strong";
}

/** Il valore proposto dal suggerimento, se è una stringa. */
export function suggestedValue(i: Issue): string {
  const to = i.suggested_fix_json?.to;
  return typeof to === "string" ? to : "";
}

/** Bozze digitate a mano, per id issue. Vivono nella pagina (non nella riga),
 *  così i comandi massivi le vedono. */
export type Drafts = Record<number, string>;

export interface AcceptPlan {
  /** Accettate cambiando solo lo stato: il suggerimento resta com'è. */
  statusIds: number[];
  /** Accettate scrivendo un valore digitato a mano (POST /bulk-fix). */
  fixes: { id: number; value: string }[];
  /** Aperte ma senza nulla da applicare (campo non editabile, valore vuoto). */
  skipped: number;
  /** Quante verranno accettate in tutto. */
  total: number;
}

/**
 * Decide, per ogni issue APERTA della lista, come accettarla:
 * - copertina / svuotamento / quarantena: cambio di stato (hanno già la fix);
 * - campo retaggabile con valore digitato diverso dal suggerimento: fix;
 * - campo retaggabile col suggerimento lasciato com'è: cambio di stato, così
 *   il suggested_fix_json originale (from/source/confidence) resta intatto;
 * - il resto è saltato e contato.
 * Le issue non aperte sono fuori dal piano (né fatte né saltate).
 */
export function planAccept(issues: Issue[], drafts: Drafts): AcceptPlan {
  const statusIds: number[] = [];
  const fixes: { id: number; value: string }[] = [];
  let skipped = 0;
  for (const i of issues) {
    if (i.status !== "open") continue;
    const action = i.suggested_fix_json?.action;
    if (i.type === "missing_cover" || action === "clear" || action === "quarantine") {
      if (i.suggested_fix_json) statusIds.push(i.id); else skipped++;
      continue;
    }
    if (i.field == null || !RETAGGABLE.has(i.field)) { skipped++; continue; }
    const suggested = suggestedValue(i);
    const value = (drafts[i.id] ?? suggested).trim();
    if (!value) { skipped++; continue; }
    if (i.suggested_fix_json && value === suggested) statusIds.push(i.id);
    else fixes.push({ id: i.id, value });
  }
  return { statusIds, fixes, skipped, total: statusIds.length + fixes.length };
}

/**
 * Rango dei gruppi, calcolato su TUTTE le issue (ogni stato): accettare o
 * ignorare una riga non lo cambia, quindi i gruppi non si scavalcano sotto
 * il mouse. Per tipo: totale decrescente, spareggio alfabetico. Per gravità:
 * ordine fisso error → warning → info.
 */
export function groupOrder(all: Issue[], groupBy: GroupBy): (key: string) => number {
  if (groupBy === "severity") return (key) => SEV_ORDER[key] ?? 9;
  const totals = new Map<string, number>();
  for (const i of all) totals.set(i.type, (totals.get(i.type) ?? 0) + 1);
  const ranked = [...totals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([k]) => k);
  const rank = new Map(ranked.map((k, idx) => [k, idx]));
  return (key) => rank.get(key) ?? ranked.length;
}
