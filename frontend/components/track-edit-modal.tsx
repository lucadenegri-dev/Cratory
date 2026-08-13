"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import { apiGet, updateTrack, type Track, type TrackDetail, type TrackUpdate } from "@/lib/api";
import { updateFileTags, type EditableTags } from "@/lib/organize/api";
import { Modal, Button, Field, Input, Alert, Spinner } from "@/components/ui";
import { TrackCover } from "@/components/track-cover";
import { useT, type Dictionary } from "@/lib/i18n";

const CAMELOT_KEYS = [
  ...Array.from({ length: 12 }, (_, i) => `${i + 1}A`),
  ...Array.from({ length: 12 }, (_, i) => `${i + 1}B`),
];

type FieldType = "number" | "int" | "text";
type Key = keyof TrackUpdate;

const FIELD_KEYS: Key[] = ["title", "artist", "album", "bpm", "camelot_key", "genre", "label", "year"];

// Campi descrittivi: su una traccia posseduta scrivono i TAG DEL FILE via
// l'endpoint Organize (single writer); sul lead restano campi della Track.
const FILE_FIELDS = new Set<Key>(["genre", "album", "label", "year"]);

function buildFields(t: Dictionary): { key: Key; label: string; type: FieldType; hint?: string; min?: number; max?: number; placeholder?: string; full?: boolean }[] {
  return [
    // Titolo e artista sono identità editoriale (correzione manuale nel DB di
    // Cratory, il file non viene toccato): riga intera, sopra ai valori tecnici.
    { key: "title", label: t.tracks.rowTitle, type: "text", full: true },
    { key: "artist", label: t.tracks.rowArtist, type: "text", full: true },
    { key: "album", label: t.tracks.rowAlbum, type: "text", full: true },
    { key: "bpm", label: "BPM", type: "number", placeholder: "128", min: 1, max: 400 },
    { key: "camelot_key", label: t.tracks.fieldKeyLabel, type: "text", placeholder: "8A", hint: t.tracks.fieldKeyHint },
    { key: "genre", label: t.tracks.rowGenre, type: "text", placeholder: t.tracks.fieldGenrePlaceholder },
    { key: "label", label: t.tracks.rowLabel, type: "text", placeholder: t.tracks.fieldLabelPlaceholder },
    { key: "year", label: t.tracks.rowYear, type: "int", placeholder: "2024", min: 0, max: 3000 },
  ];
}

const CAMELOT_RE = /^\d{1,2}[AB]$/;

function initialForm(track: Track): Record<string, string> {
  const f: Record<string, string> = {};
  for (const key of FIELD_KEYS) {
    const v = (track as unknown as Record<string, unknown>)[key];
    f[key] = v === null || v === undefined ? "" : String(v);
  }
  return f;
}

/** Wrapper: monta il form solo quando aperto e lo rigenera per ogni traccia. */
export function TrackEditModal({ track, open, onClose, onSaved }: {
  track: Track | null;
  open: boolean;
  onClose: () => void;
  onSaved: (t: TrackDetail) => void;
}) {
  if (!open || !track) return null;
  return <EditForm key={track.id} track={track} onClose={onClose} onSaved={onSaved} />;
}

function EditForm({ track, onClose, onSaved }: { track: Track; onClose: () => void; onSaved: (t: TrackDetail) => void }) {
  const t = useT();
  const FIELDS = buildFields(t);
  const [initial] = useState(() => initialForm(track));
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const camelotInvalid = form.camelot_key.trim() !== "" && !CAMELOT_RE.test(form.camelot_key.trim().toUpperCase());
  const set = (k: string, v: string) => setForm((cur) => ({ ...cur, [k]: v }));

  async function save() {
    if (camelotInvalid) return;
    const toFile = track.primary_file_id != null;
    const trackPatch: TrackUpdate = {};
    const filePatch: Partial<EditableTags> = {};
    for (const { key, type } of FIELDS) {
      const raw = form[key].trim();
      if (raw === initial[key].trim()) continue; // invia solo i campi cambiati
      if (toFile && FILE_FIELDS.has(key)) {
        (filePatch as Record<string, string>)[key] = raw; // "" svuota il tag
      } else if (raw === "") {
        (trackPatch as Record<string, unknown>)[key] = null;
      } else if (type === "text") {
        (trackPatch as Record<string, unknown>)[key] = key === "camelot_key" ? raw.toUpperCase() : raw;
      } else {
        (trackPatch as Record<string, unknown>)[key] = Number(raw);
      }
    }
    if (Object.keys(trackPatch).length === 0 && Object.keys(filePatch).length === 0) { onClose(); return; }
    setBusy(true);
    setError(null);
    // Due percorsi di scrittura indipendenti: l'errore di uno non deve
    // mascherare l'esito dell'altro.
    const errors: string[] = [];
    if (Object.keys(filePatch).length > 0) {
      try { await updateFileTags(track.primary_file_id!, filePatch); }
      catch (e) { errors.push(`${t.tracks.fileTagsErrorPrefix}: ${String((e as Error).message ?? e)}`); }
    }
    if (Object.keys(trackPatch).length > 0) {
      try { await updateTrack(track.id, trackPatch); }
      catch (e) { errors.push(`${t.tracks.trackErrorPrefix}: ${String((e as Error).message ?? e)}`); }
    }
    try {
      // Ricarica gli effettivi (il salvataggio file risponde un FileRow, non una Track).
      onSaved(await apiGet<TrackDetail>(`/api/tracks/${track.id}`));
    } catch { /* la lista si riallineerà da sola al prossimo load */ }
    setBusy(false);
    if (errors.length > 0) setError(errors.join(" — "));
    else onClose();
  }

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={t.tracks.editValues}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          {/* Fuori dal <form> (il footer della Modal è un fratello del body):
              l'attributo form= lo associa comunque come submit button. */}
          <Button type="submit" form="track-edit-form" disabled={busy || camelotInvalid}>
            {busy ? <Spinner /> : <Save size={15} />} {t.common.save}
          </Button>
        </>
      }
    >
      <div className="mb-4 flex items-center gap-3">
        <TrackCover track={track} className="h-11 w-11" iconSize={18} />
        <div className="min-w-0">
          <div className="truncate font-medium">{track.title ?? <span className="italic text-faint">{t.tracks.untitledLower}</span>}</div>
          <div className="truncate text-sm text-muted">{track.artist ?? "—"}</div>
        </div>
      </div>

      <p className="mb-4 text-xs text-muted">
        {t.tracks.manualValuesHint}
      </p>
      {track.primary_file_id != null && (
        <p className="-mt-2 mb-4 text-xs text-muted">{t.tracks.fileTagsHint}</p>
      )}

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <datalist id="camelot-keys">
        {CAMELOT_KEYS.map((k) => <option key={k} value={k} />)}
      </datalist>

      <form
        id="track-edit-form"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3"
        onSubmit={(e) => { e.preventDefault(); void save(); }}
      >
        {FIELDS.map((f) => (
          <div key={f.key} className={f.full ? "col-span-2 sm:col-span-3" : undefined}>
            <Field
              label={f.label}
              hint={f.key === "camelot_key" && camelotInvalid ? <span className="text-danger">{t.tracks.invalidKeyNotation}</span> : f.hint}
            >
              <Input
                type={f.type === "text" ? "text" : "number"}
                inputMode={f.type === "int" ? "numeric" : undefined}
                step={f.type === "number" ? "0.1" : undefined}
                min={f.min}
                max={f.max}
                placeholder={f.placeholder}
                list={f.key === "camelot_key" ? "camelot-keys" : undefined}
                value={form[f.key]}
                onChange={(e) => set(f.key, e.target.value)}
                className={f.key === "camelot_key" && camelotInvalid ? "border-danger/60" : undefined}
              />
            </Field>
          </div>
        ))}
      </form>
    </Modal>
  );
}
