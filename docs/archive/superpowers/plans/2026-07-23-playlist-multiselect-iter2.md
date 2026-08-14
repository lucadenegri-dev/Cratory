# Playlist da libreria — Iterazione 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rifinire la creazione playlist da libreria: filtro playlist **multi-selezione** (unione), **pannello "Selezionate"** sempre visibile, tracce **già presenti nel target non selezionabili**, e **conferma evidente** dopo l'ADD (import-manual + popover dettaglio traccia).

**Architecture:** Backend: `in_playlist` diventa multi-valore su `GET /api/tracks`. Frontend: `apiGet` supporta parametri array; la modalità library di import-manual passa a `inPlaylists: Set<number>` (popover a checkbox) e `selectedTracks: Map<number, Track>` (pannello + label), carica la membership del target per marcare "già presente"; il popover del dettaglio mostra una riga di conferma.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite); Next.js 16 client components, design-system in `frontend/components/ui.tsx`, i18n it/en.

## Global Constraints

- Commit: NO `Co-Authored-By`. Branch corrente `feat/playlist-da-libreria-multiselect` (verifica `git rev-parse --abbrev-ref HEAD`); stagea solo i file del task.
- Backend test TDD: `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`. Fixture `client_db` come in `backend/tests/test_tracks_in_playlist_filter.py`.
- Frontend: leggi `frontend/CLAUDE.md` prima di editare (Next 16 modificato). Ogni stringa via `useT()`; chiavi i18n in **entrambi** `it.ts` e `en.ts` con stessa forma/arità. Componenti da `@/components/ui`. Token colore validi: `bg-elevated`, `bg-surface`, `bg-bg`, `text-muted`, `text-fg`, `text-faint`, `text-fg-strong`, `text-danger`, `border-border`.
- Frontend verify: `cd frontend && npm run lint && npm run build`. NON avviare dev server: la verifica live la fa il controller dopo la review.
- Membership invariata: `added_by="cratory"`, nessun tocco ai file audio.

---

### Task 7: Backend — filtro `in_playlist` multi-valore

**Files:**
- Modify: `backend/app/repositories.py` (`_apply_track_filters`, param `in_playlist`)
- Modify: `backend/app/routers/tracks.py` (`get_tracks`, param `in_playlist`)
- Test: `backend/tests/test_tracks_in_playlist_filter.py` (aggiungi un test unione)

**Interfaces:**
- Produces: `GET /api/tracks?in_playlist=1&in_playlist=2` → tracce che appartengono a **una qualsiasi** delle playlist (unione). Il caso singolo `?in_playlist=8` resta valido (FastAPI → `[8]`).

- [ ] **Step 1: Write the failing test** — aggiungi in `test_tracks_in_playlist_filter.py`:

```python
def test_in_playlist_unione_di_piu_playlist(client_db):
    client, db = client_db
    pa = Playlist(platform="manual", name="A", kind="manual")
    pb = Playlist(platform="manual", name="B", kind="manual")
    db.add_all([pa, pb]); db.flush()
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    add_track_to_playlist(db, a, pa)
    add_track_to_playlist(db, b, pb)
    db.commit()  # c non e' in nessuna delle due

    r = client.get("/api/tracks", params={"in_playlist": [pa.id, pb.id]})
    assert r.status_code == 200
    assert sorted(t["title"] for t in r.json()["items"]) == ["a", "b"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_in_playlist_filter.py -v`
Expected: il nuovo test FALLISce (con `in_playlist: int` FastAPI 422 o il primo valore soltanto).

- [ ] **Step 3a: `_apply_track_filters`** — cambia la firma del param e la clausola in `backend/app/repositories.py`:

Firma: da `in_playlist: int | None = None,` a `in_playlist: list[int] | None = None,`.
Clausola (sostituisci quella esistente):

```python
    if in_playlist:
        stmt = stmt.where(Track.id.in_(
            select(playlist_tracks.c.track_id).where(
                playlist_tracks.c.playlist_id.in_(in_playlist)
            )
        ))
```

(`if in_playlist:` copre sia `None` sia lista vuota.)

- [ ] **Step 3b: router** — in `backend/app/routers/tracks.py`, cambia il param di `get_tracks` da `in_playlist: int | None = None,` a:

```python
    in_playlist: list[int] | None = Query(default=None),
```

`Query` è già importato. La riga che lo passa a `list_tracks(... in_playlist=in_playlist, ...)` resta invariata.

- [ ] **Step 4: Run to verify it passes** — l'intero file (nuovo + i due esistenti):

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_in_playlist_filter.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/routers/tracks.py backend/tests/test_tracks_in_playlist_filter.py
git commit -m "feat(tracks): filtro in_playlist multi-valore (unione)"
```

---

### Task 8: Frontend — `apiGet` array + filtro playlist multi-selezione + pannello "Selezionate"

**Files:**
- Modify: `frontend/lib/api/client.ts` (`apiGet` supporta valori array)
- Create: `frontend/components/playlist-filter-menu.tsx` (popover a checkbox)
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (blocco `playlists.importManual`)
- Modify: `frontend/app/playlists/import-manual/page.tsx`

**Interfaces:**
- Consumes: `in_playlist` multi-valore (Task 7).
- Produces: `apiGet` accetta `(string|number)[]` come valore param → chiavi ripetute. Componente `PlaylistFilterMenu`. Stato `inPlaylists: Set<number>`, `selectedTracks: Map<number, Track>`.

- [ ] **Step 1: Estendi `apiGet` per i valori array** — in `frontend/lib/api/client.ts`, cambia il tipo di `params` e il loop:

Tipo: `params?: Record<string, string | number | boolean | undefined | (string | number)[]>,`
Loop (sostituisci il corpo del `for`):

```ts
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === "") continue;
      if (Array.isArray(v)) {
        for (const item of v) qs.append(k, String(item));
      } else {
        qs.set(k, String(v));
      }
    }
```

(Backward compatible: i valori scalari usano ancora `set`.)

- [ ] **Step 2: i18n (it.ts)** — nel blocco `importManual`, aggiungi:

```ts
      playlistFilterButton: (n: number) => (n === 0 ? "Tutte le playlist" : `${n} playlist`),
      selectedPanelTitle: (n: number) => `Selezionate (${n})`,
      emptySelectionHint: "Nessuna traccia selezionata.",
```

- [ ] **Step 3: i18n (en.ts)** — stesse chiavi:

```ts
      playlistFilterButton: (n: number) => (n === 0 ? "All playlists" : `${n} playlist${n > 1 ? "s" : ""}`),
      selectedPanelTitle: (n: number) => `Selected (${n})`,
      emptySelectionHint: "No tracks selected.",
```

- [ ] **Step 4: Crea `PlaylistFilterMenu`** — `frontend/components/playlist-filter-menu.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Playlist } from "@/lib/api";
import { Button } from "@/components/ui";

/** Trigger + popover a checkbox per selezionare piu' playlist (filtro unione). */
export function PlaylistFilterMenu({ playlists, selected, onToggle, label }: {
  playlists: Playlist[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <Button type="button" variant="outline" className="h-9 w-full justify-between" onClick={() => setOpen((o) => !o)}>
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className="shrink-0" />
      </Button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 max-h-60 w-full min-w-48 overflow-y-auto border border-border bg-elevated p-1 shadow-lg">
          {playlists.length === 0 && <p className="px-2 py-3 text-center text-xs text-muted">—</p>}
          {playlists.map((p) => (
            <label key={p.id} className="flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm hover:bg-surface">
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggle(p.id)} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">{p.name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
```

If `Button` doesn't render `w-full justify-between` cleanly (check `frontend/components/ui.tsx`), fall back to a plain styled `<button>` with the same look as the `h-9` filter inputs — match the existing filter row visually. Note the choice in your report.

- [ ] **Step 5: import-manual — stato** — in `frontend/app/playlists/import-manual/page.tsx`:

Import: aggiungi `PlaylistFilterMenu` (`import { PlaylistFilterMenu } from "@/components/playlist-filter-menu";`). Rimuovi `Select` dall'import UI **solo se** non più usato altrove nel file (il target "Aggiungi a esistente" lo usa ancora → **tienilo**).

Sostituisci lo stato:
- `const [inPlaylist, setInPlaylist] = useState("");` → `const [inPlaylists, setInPlaylists] = useState<Set<number>>(new Set());`
- `const [selected, setSelected] = useState<Set<number>>(new Set());` → `const [selectedTracks, setSelectedTracks] = useState<Map<number, Track>>(new Map());`

Helper di supporto (vicino alle altre):

```ts
  const togglePlaylist = (id: number) =>
    setInPlaylists((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
```

- [ ] **Step 6: import-manual — effetti e azioni** — aggiorna:

Effetto lista (la `apiGet` con `limit: 50`): sostituisci `in_playlist: inPlaylist || undefined,` con `in_playlist: inPlaylists.size ? [...inPlaylists] : undefined,`. Dep array: sostituisci `inPlaylist` con `inPlaylists`.

`toggle` ora riceve la Track:
```ts
  const toggle = (tr: Track) =>
    setSelectedTracks((m) => {
      const next = new Map(m);
      if (next.has(tr.id)) next.delete(tr.id); else next.set(tr.id, tr);
      return next;
    });
```

`selectAllMatching` (usa `limit: 0`, mappa per id→Track, stesso `in_playlist` array):
```ts
  const selectAllMatching = async () => {
    try {
      const r = await apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        genre: genre || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        in_playlist: inPlaylists.size ? [...inPlaylists] : undefined,
        limit: 0,
      });
      setSelectedTracks(new Map(r.items.map((tr) => [tr.id, tr])));
    } catch {
      /* noop */
    }
  };
```

`doCreateFromLibrary` e `doAddToExisting`: sostituisci `[...selected]` con `[...selectedTracks.keys()]`, e le guard `selected.size` con `selectedTracks.size`.
`marginalia`: sostituisci `selected.size` con `selectedTracks.size`.

- [ ] **Step 7: import-manual — JSX filtro, pannello, righe** — nel ramo library:

(a) Sostituisci il `<Select>` del filtro `inPlaylist` (quello con `im.playlistFilterAllOption` e `allPlaylists.map`) con:
```tsx
                <PlaylistFilterMenu
                  playlists={allPlaylists}
                  selected={inPlaylists}
                  onToggle={togglePlaylist}
                  label={im.playlistFilterButton(inPlaylists.size)}
                />
```

(b) La barra contatore/seleziona-tutto: aggiorna `im.selectedCount(selected.size)` → `im.selectedCount(selectedTracks.size)`, il "clear" → `setSelectedTracks(new Map())` con guard `selectedTracks.size === 0`, e `selectAllMatching` invariato.

(c) Le righe della lista: la checkbox usa `selectedTracks.has(tr.id)` e `onChange={() => toggle(tr)}`.

(d) **Pannello "Selezionate (N)"** — inseriscilo subito sotto la lista risultati (prima della barra azioni). Sempre visibile:
```tsx
              <div className="border border-border">
                <div className="border-b border-border px-3 py-2 text-xs font-medium text-muted">
                  {im.selectedPanelTitle(selectedTracks.size)}
                </div>
                {selectedTracks.size === 0 ? (
                  <div className="px-3 py-4 text-center text-xs text-muted">{im.emptySelectionHint}</div>
                ) : (
                  <ul className="max-h-48 divide-y divide-border overflow-y-auto">
                    {[...selectedTracks.values()].map((tr) => (
                      <li key={tr.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                        <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                        <button type="button" onClick={() => toggle(tr)} aria-label={im.removeAria} className="shrink-0 text-muted hover:text-fg">✕</button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
```
(`im.removeAria` è una chiave esistente = "Rimuovi"/"Remove" — riutilizzala.)

- [ ] **Step 8: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 9: Self-review** — nessun riferimento residuo a `inPlaylist`/`setInPlaylist`/`selected`/`setSelected`; il filtro invia `in_playlist` array; il pannello elenca `selectedTracks.values()` con rimozione; create/add usano `[...selectedTracks.keys()]`; `Select` ancora importato/usato per il target.

- [ ] **Step 10: Commit**

```bash
git add frontend/lib/api/client.ts frontend/components/playlist-filter-menu.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/app/playlists/import-manual/page.tsx
git commit -m "feat(import-manual): filtro playlist multi-selezione + pannello selezionate"
```

---

### Task 9: Frontend — già presenti nel target non selezionabili + conferma evidente

**Files:**
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (blocco `playlists.importManual`)
- Modify: `frontend/app/playlists/import-manual/page.tsx`

**Interfaces:**
- Consumes: `playlistTracks(id)` (già in `@/lib/api`, ritorna `Track[]`), lo stato di Task 8.

- [ ] **Step 1: i18n (it.ts + en.ts)** — aggiungi nel blocco `importManual`:
  - it.ts: `alreadyInTarget: "già presente",`
  - en.ts: `alreadyInTarget: "already in",`

- [ ] **Step 2: Stato + effetto membership target** — in `import-manual/page.tsx`:

Import: aggiungi `playlistTracks` all'import da `@/lib/api`.
Stato: `const [targetMemberIds, setTargetMemberIds] = useState<Set<number>>(new Set());`
Effetto:
```ts
  useEffect(() => {
    if (!addTarget) { setTargetMemberIds(new Set()); return; }
    let alive = true;
    playlistTracks(Number(addTarget))
      .then((tracks) => { if (alive) setTargetMemberIds(new Set(tracks.map((t) => t.id))); })
      .catch(() => { if (alive) setTargetMemberIds(new Set()); });
    return () => { alive = false; };
  }, [addTarget]);
```

- [ ] **Step 3: Righe non selezionabili** — nel `results.map`, calcola `const already = targetMemberIds.has(tr.id);` e rendi la riga:
```tsx
                {results.map((tr) => {
                  const already = targetMemberIds.has(tr.id);
                  return (
                    <label
                      key={tr.id}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors ${already ? "cursor-default opacity-50" : "cursor-pointer hover:bg-elevated"}`}
                    >
                      <input
                        type="checkbox"
                        checked={!already && selectedTracks.has(tr.id)}
                        disabled={already}
                        onChange={() => toggle(tr)}
                        className="shrink-0"
                      />
                      <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                      {already && <Badge tone="neutral">{im.alreadyInTarget}</Badge>}
                      {tr.has_local_file && !already && <Badge tone="success">FILE</Badge>}
                    </label>
                  );
                })}
```

- [ ] **Step 4: `selectAllMatching` esclude i già-presenti** — dopo il fetch, filtra:
```ts
      setSelectedTracks(new Map(
        r.items.filter((tr) => !targetMemberIds.has(tr.id)).map((tr) => [tr.id, tr]),
      ));
```

- [ ] **Step 5: Conferma + refresh dopo ADD** — riscrivi `doAddToExisting`:
```ts
  const doAddToExisting = async () => {
    if (!addTarget) return;
    setError(null);
    setFeedback(null);
    setBusy(true);
    try {
      const res = await addTracksToPlaylist(Number(addTarget), [...selectedTracks.keys()]);
      setFeedback(t.playlists.importManual.addedFeedback(res.added, res.skipped));
      // Le tracce aggiunte ora fanno parte del target: aggiorna i badge e svuota la selezione.
      const refreshed = await playlistTracks(Number(addTarget));
      setTargetMemberIds(new Set(refreshed.map((tr) => tr.id)));
      setSelectedTracks(new Map());
      setBusy(false);
    } catch (e) {
      setError(t.playlists.importManual.addFailed(errText(e)));
      setBusy(false);
    }
  };
```

- [ ] **Step 6: Conferma visibile vicino ai pulsanti** — sposta il blocco `{feedback && <Alert tone="success">{feedback}</Alert>}` da inizio ramo library a **subito sopra** la barra azioni (il `div` con i pulsanti Add/Create), così è nel campo visivo dopo il click. (Un solo punto di render: rimuovi quello in alto.)

- [ ] **Step 7: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/app/playlists/import-manual/page.tsx
git commit -m "feat(import-manual): gia'-presente nel target non selezionabile + conferma ADD"
```

---

### Task 10: Frontend — popover dettaglio traccia: riga di conferma

**Files:**
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (blocco `tracks`)
- Modify: `frontend/components/add-to-playlist-menu.tsx`

**Interfaces:**
- Consumes: lo stato del componente esistente.

- [ ] **Step 1: i18n (tracks)** — aggiungi:
  - it.ts: `addedToPlaylist: (name: string) => \`Aggiunta a ${name}\`,` e `createdPlaylist: (name: string) => \`Creata ${name}\`,`
  - en.ts: `addedToPlaylist: (name: string) => \`Added to ${name}\`,` e `createdPlaylist: (name: string) => \`Created ${name}\`,`

- [ ] **Step 2: Stato + messaggi** — in `frontend/components/add-to-playlist-menu.tsx`:

Aggiungi `const [success, setSuccess] = useState<string | null>(null);`
In `addTo`, nel `try` dopo `onChanged()`: `setSuccess(t.tracks.addedToPlaylist(pl.name));`
In `createAndAdd`, nel `try` dopo `onChanged()` (prima di chiudere il form): `setSuccess(t.tracks.createdPlaylist(newName.trim()));`
Azzera `success` quando riparte un'azione (all'inizio di `addTo`/`createAndAdd`: `setSuccess(null);`) e quando il popover si chiude (nell'effetto `[open]` che ricarica, se `!open` non serve; aggiungi `setSuccess(null)` all'apertura).

- [ ] **Step 3: Render** — sotto il blocco `{error && ...}` nel popover, aggiungi:
```tsx
          {success && <p className="px-2 py-1 text-xs text-fg">{success}</p>}
```

- [ ] **Step 4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/components/add-to-playlist-menu.tsx
git commit -m "feat(tracks): conferma nel popover aggiungi a playlist"
```

---

## Self-Review

**Spec coverage (iterazione 2):**
- Filtro playlist multi-selezione (unione) → Task 7 (backend) + Task 8 (apiGet array + PlaylistFilterMenu + inPlaylists). ✅
- Pannello "Selezionate" con rimozione → Task 8 (selectedTracks Map + pannello). ✅
- Già presenti nel target non selezionabili → Task 9. ✅
- Conferma evidente dopo ADD (import-manual) → Task 9 (feedback vicino ai pulsanti + refresh badge + svuota selezione). ✅
- Conferma nel popover dettaglio → Task 10. ✅

**Type consistency:** `inPlaylists: Set<number>` (togglePlaylist, PlaylistFilterMenu selected/onToggle), `selectedTracks: Map<number, Track>` (toggle(tr), keys() per gli id, values() per il pannello), `targetMemberIds: Set<number>` (da `playlistTracks` → Track[].map(id)); `apiGet` accetta `(string|number)[]` → `in_playlist: [...inPlaylists]`. `playlistTracks(id): Promise<Track[]>` esistente.

**Placeholder scan:** nessun TBD; ogni step ha codice/comando concreto. La chiave i18n `removeAria` riusata (era orfana da iter-1 → rientra in uso).
