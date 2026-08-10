"use client";

import { useState } from "react";
import { updateFileTags, type FileRow, type LibraryFacets, type EditableTags } from "@/lib/api";
import { Modal, Button, Input, Field, Alert } from "@/components/ui";
import { useT } from "@/lib/i18n";

const FIELDS: (keyof EditableTags)[] = [
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
];
// campi con autocomplete dai facet della libreria (riusa quelli già caricati)
const FACET_FIELDS = new Set<keyof EditableTags>(["genre", "artist", "album", "label"]);
const NUM_FIELDS = new Set<keyof EditableTags>(["year", "track_no"]);

function initial(row: FileRow): EditableTags {
  return {
    artist: row.artist ?? "",
    title: row.title ?? "",
    album: row.album ?? "",
    album_artist: row.album_artist ?? "",
    genre: row.genre ?? "",
    year: row.year != null ? String(row.year) : "",
    label: row.label ?? "",
    track_no: row.track_no != null ? String(row.track_no) : "",
    comment: row.comment ?? "",
  };
}

export function FileEditPanel({ row, facets, onClose, onSaved }: {
  row: FileRow;
  facets: LibraryFacets | null;
  onClose: () => void;
  onSaved: (updated: FileRow) => void;
}) {
  const t = useT();
  const base = initial(row);
  const [form, setForm] = useState<EditableTags>(base);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const badNum = (f: keyof EditableTags) =>
    NUM_FIELDS.has(f) && form[f].trim() !== "" && !/^\d+$/.test(form[f].trim());
  const anyBadNum = FIELDS.some(badNum);
  const changed = FIELDS.filter((f) => form[f].trim() !== base[f].trim());

  const facetFor = (f: keyof EditableTags): string[] =>
    facets && FACET_FIELDS.has(f)
      ? (facets[f as keyof LibraryFacets] as (string | number)[]).map(String)
      : [];

  const save = async () => {
    if (changed.length === 0 || anyBadNum) return;
    setSaving(true);
    setError(null);
    try {
      const patch: Partial<EditableTags> = {};
      for (const f of changed) patch[f] = form[f].trim();
      const updated = await updateFileTags(row.id, patch);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={t.files.editTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t.common.cancel}</Button>
          <Button onClick={save} disabled={saving || changed.length === 0 || anyBadNum}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="truncate text-[11px] text-faint" dir="rtl" title={row.path}>{row.path}</p>
        {error && <Alert>{error}</Alert>}
        {FIELDS.map((f) => {
          const opts = facetFor(f);
          const listId = `edit-${f}`;
          return (
            <Field key={f} label={t.files.field[f]} hint={badNum(f) ? t.files.numHint : undefined}>
              <Input
                list={opts.length ? listId : undefined}
                value={form[f]}
                aria-invalid={badNum(f) || undefined}
                onChange={(e) => setForm((s) => ({ ...s, [f]: e.target.value }))}
              />
              {opts.length > 0 && (
                <datalist id={listId}>
                  {opts.map((o) => <option key={o} value={o} />)}
                </datalist>
              )}
            </Field>
          );
        })}
      </div>
    </Modal>
  );
}
