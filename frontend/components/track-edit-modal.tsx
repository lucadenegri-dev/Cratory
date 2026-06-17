"use client";

import { useState } from "react";
import { Music4, Save } from "lucide-react";
import { updateTrack, type Track, type TrackUpdate } from "@/lib/api";
import { Modal, Button, Field, Input, Alert, Spinner } from "@/components/ui";

const CAMELOT_KEYS = [
  ...Array.from({ length: 12 }, (_, i) => `${i + 1}A`),
  ...Array.from({ length: 12 }, (_, i) => `${i + 1}B`),
];

type FieldType = "number" | "int" | "text";
type Key = keyof TrackUpdate;

const FIELDS: { key: Key; label: string; type: FieldType; hint?: string; min?: number; max?: number; placeholder?: string }[] = [
  { key: "bpm", label: "BPM", type: "number", placeholder: "128", min: 1, max: 400 },
  { key: "camelot_key", label: "Tonalità (Camelot)", type: "text", placeholder: "8A", hint: "es. 8A, 12B" },
  { key: "energy", label: "Energia", type: "int", placeholder: "0–100", min: 0, max: 100 },
  { key: "mood", label: "Mood", type: "text", placeholder: "es. dark, euphoric" },
  { key: "danceability", label: "Danceability", type: "int", placeholder: "0–100", min: 0, max: 100 },
  { key: "vocalness", label: "Vocalness", type: "int", placeholder: "0–100", min: 0, max: 100 },
  { key: "genre", label: "Genere", type: "text", placeholder: "es. techno" },
  { key: "label", label: "Etichetta", type: "text", placeholder: "es. Kompakt" },
  { key: "year", label: "Anno", type: "int", placeholder: "2024", min: 0, max: 3000 },
];

const CAMELOT_RE = /^\d{1,2}[AB]$/;

function initialForm(t: Track): Record<string, string> {
  const f: Record<string, string> = {};
  for (const { key } of FIELDS) {
    const v = (t as unknown as Record<string, unknown>)[key];
    f[key] = v === null || v === undefined ? "" : String(v);
  }
  return f;
}

/** Wrapper: monta il form solo quando aperto e lo rigenera per ogni traccia. */
export function TrackEditModal({ track, open, onClose, onSaved }: {
  track: Track | null;
  open: boolean;
  onClose: () => void;
  onSaved: (t: Track) => void;
}) {
  if (!open || !track) return null;
  return <EditForm key={track.id} track={track} onClose={onClose} onSaved={onSaved} />;
}

function EditForm({ track, onClose, onSaved }: { track: Track; onClose: () => void; onSaved: (t: Track) => void }) {
  const [initial] = useState(() => initialForm(track));
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const camelotInvalid = form.camelot_key.trim() !== "" && !CAMELOT_RE.test(form.camelot_key.trim().toUpperCase());
  const set = (k: string, v: string) => setForm((cur) => ({ ...cur, [k]: v }));

  async function save() {
    if (camelotInvalid) return;
    const patch: TrackUpdate = {};
    for (const { key, type } of FIELDS) {
      const raw = form[key].trim();
      if (raw === initial[key].trim()) continue; // invia solo i campi cambiati
      if (raw === "") {
        (patch as Record<string, unknown>)[key] = null;
      } else if (type === "text") {
        (patch as Record<string, unknown>)[key] = key === "camelot_key" ? raw.toUpperCase() : raw;
      } else {
        (patch as Record<string, unknown>)[key] = Number(raw);
      }
    }
    if (Object.keys(patch).length === 0) { onClose(); return; }
    setBusy(true);
    setError(null);
    try {
      onSaved(await updateTrack(track.id, patch));
      onClose();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Modifica valori"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Annulla</Button>
          <Button onClick={save} disabled={busy || camelotInvalid}>
            {busy ? <Spinner /> : <Save size={15} />} Salva
          </Button>
        </>
      }
    >
      <div className="mb-4 flex items-center gap-3">
        {track.album_art_url
          ? <img src={track.album_art_url} alt="" className="h-11 w-11 shrink-0 rounded object-cover" />
          : <span className="grid h-11 w-11 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={18} /></span>}
        <div className="min-w-0">
          <div className="truncate font-medium">{track.title ?? <span className="italic text-faint">senza titolo</span>}</div>
          <div className="truncate text-sm text-muted">{track.artist ?? "—"}</div>
        </div>
      </div>

      <p className="mb-4 text-xs text-faint">
        I valori inseriti a mano hanno la precedenza sull&apos;arricchimento automatico. Lascia un campo vuoto per azzerarlo.
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <datalist id="camelot-keys">
        {CAMELOT_KEYS.map((k) => <option key={k} value={k} />)}
      </datalist>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {FIELDS.map((f) => (
          <Field
            key={f.key}
            label={f.label}
            hint={f.key === "camelot_key" && camelotInvalid ? <span className="text-danger">notazione non valida</span> : f.hint}
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
        ))}
      </div>
    </Modal>
  );
}
