# Wishlist (rifacimento Download) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trasformare `/downloads` nella pagina `/wishlist`: gestione di tutte le tracce non possedute, con stato download per traccia, provenienza (chip playlist), acquisto via link ai negozi e archiviazione reversibile.

**Architecture:** Backend quasi intatto — un solo cambio (`archived` nel `PATCH /api/tracks/{id}`); la lista arriva da `GET /api/tracks?has_local_file=false&limit=0` che include già `playlists` e `last_download_*`. Frontend: nuova pagina `app/wishlist/page.tsx` composta da una riga estratta (`components/wishlist-row.tsx`), un helper puro per lo stato (`lib/wishlist-status.ts`), link negozi (`lib/store-links.ts`) e un nuovo primitivo `DropdownMenu` in `components/ui.tsx`. `/downloads` viene rimossa e reindirizzata.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (backend); Next.js 16 App Router, React, Tailwind, vitest + testing-library, Playwright (frontend).

**Spec:** `docs/superpowers/specs/2026-07-19-wishlist-redesign-design.md`

## Global Constraints

- Worktree: si lavora in `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774` (branch `claude/wishlist-download-redesign-2ac774`). Tutti i path sotto sono relativi a questa root.
- Backend venv: il worktree non ha `.venv`; usare quello del checkout principale: `/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python`. Lanciare pytest con cwd = `<worktree>/backend` (il conftest inserisce la dir backend del worktree in `sys.path`, quindi testa il codice del worktree).
- Frontend: prima di qualunque task frontend serve `npm install` in `<worktree>/frontend` (node_modules non esiste nei worktree). Next 16 ha breaking changes: leggere `frontend/CLAUDE.md` e, in caso di dubbi su API Next (redirects, Suspense), la doc in `frontend/node_modules/next/dist/docs/` dopo l'install.
- Next 16 mangia gli spazi JSX a fine riga: usare `{" "}` esplicito se un testo inline va a capo nel sorgente.
- Commit: messaggi in italiano, stile `feat(wishlist): …` come lo storico. **MAI aggiungere Co-Authored-By.**
- i18n: `Dictionary = typeof en` (`frontend/lib/i18n/en.ts:1057`): ogni chiave nuova va aggiunta **prima** in `en.ts` poi in `it.ts`, identica struttura.
- Test unit frontend: vitest + `@testing-library/react`, file in `frontend/tests/*.test.{ts,tsx}`, `afterEach(cleanup)` (vedi `frontend/tests/ui-primitives.test.tsx`).
- Test backend: niente TestClient — chiamate dirette a repository/router (stile `backend/tests/test_track_update.py`).
- Nessuna AI, nessuna nuova dipendenza, nessuna migrazione di schema.

---

### Task 1: Backend — `archived` nel PATCH traccia

**Files:**
- Modify: `backend/app/schemas.py` (classe `TrackUpdateIn`, righe ~58-81)
- Modify: `backend/app/routers/tracks.py` (funzione `patch_track`, righe ~131-154)
- Test: `backend/tests/test_track_archive_patch.py` (nuovo)

**Interfaces:**
- Consumes: `repositories.update_track(db, track, data)` esistente (un `setattr` per campo — `archived: bool` passa senza modifiche), `repositories.list_tracks(db, archived=...)` esistente.
- Produces: `PATCH /api/tracks/{id}` accetta `{"archived": true|false}`; `null` o campo assente = invariato. È il contratto usato dal frontend nel Task 5 (`updateTrack(id, { archived: true })`).

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_track_archive_patch.py`:

```python
"""Archivia/ripristina dalla wishlist: campo `archived` nel PATCH /api/tracks/{id}.

Prima via manuale per impostare Track.archived (finora solo DJPlayer/indicizzazione).
Semantica PATCH: campo assente O null = invariato (archived e' un bool NOT NULL:
il "null azzera" degli altri campi qui non si applica). Stile test_track_update.py:
chiamate dirette a router/repository, niente TestClient.
"""

from app.models import Track
from app.repositories import list_tracks
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_patch_archivia_e_ripristina(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    db.refresh(t)
    assert t.archived is True
    tracks.patch_track(t.id, TrackUpdateIn(archived=False), db)
    db.refresh(t)
    assert t.archived is False


def test_patch_senza_archived_non_tocca(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    db.refresh(t)
    assert t.archived is True  # campo assente = invariato
    assert t.title == "Nuovo"


def test_patch_archived_null_e_invariato(db):
    """`archived: null` esplicito non deve scrivere NULL su una colonna NOT NULL."""
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=None), db)
    db.refresh(t)
    assert t.archived is True


def test_lista_riflette_l_archiviazione(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    total_attive, attive = list_tracks(db, limit=0, offset=0)
    total_arch, archiviate = list_tracks(db, limit=0, offset=0, archived=True)
    assert t.id not in [x.id for x in attive]
    assert t.id in [x.id for x in archiviate]
```

Nota: verificare la firma esatta di `list_tracks` in `backend/app/repositories.py` (i kwargs `limit/offset/archived` esistono già, usati da `routers/tracks.get_tracks`); adeguare la chiamata nel test se l'ordine dei parametri differisce.

- [ ] **Step 2: Verificare che falliscano**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774/backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_track_archive_patch.py -v
```

Atteso: FAIL con `ValidationError` / `unexpected keyword argument 'archived'` (il campo non esiste in `TrackUpdateIn`, `extra="forbid"`).

- [ ] **Step 3: Implementazione minima**

In `backend/app/schemas.py`, aggiungere in coda ai campi di `TrackUpdateIn` (dopo `label`):

```python
    # Archivia/ripristina dalla wishlist. Bool NOT NULL: null = invariato
    # (il "null azzera" degli altri campi non si applica, vedi patch_track).
    archived: bool | None = None
```

In `backend/app/routers/tracks.py`, dentro `patch_track`, subito dopo `data = payload.model_dump(exclude_unset=True)`:

```python
    # `archived` e' un bool NOT NULL: un null esplicito non puo' azzerare,
    # vale come "invariato" (a differenza degli altri campi PATCH).
    if data.get("archived") is None:
        data.pop("archived", None)
```

- [ ] **Step 4: Verificare che passino + regressione**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774/backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_track_archive_patch.py tests/test_track_update.py tests/test_archived.py -v
```

Atteso: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/tracks.py backend/tests/test_track_archive_patch.py
git commit -m "feat(wishlist): archivia/ripristina via PATCH /api/tracks — prima via manuale per Track.archived"
```

---

### Task 2: Frontend — fondamenta (store links, tipo TrackUpdate, DropdownMenu)

**Files:**
- Create: `frontend/lib/store-links.ts`
- Modify: `frontend/lib/api/types.ts:134-144` (interface `TrackUpdate`)
- Modify: `frontend/components/ui.tsx` (nuovo export `DropdownMenu` in fondo al file)
- Test: `frontend/tests/store-links.test.ts` (nuovo), `frontend/tests/dropdown-menu.test.tsx` (nuovo)

**Interfaces:**
- Produces:
  - `STORES: { key: StoreKey; label: string; url: (q: string) => string }[]` e `storeQuery(artist: string | null, title: string | null): string` da `@/lib/store-links` (usati dal Task 4).
  - `DropdownMenu({ label, items, disabled }: { label: ReactNode; items: MenuItem[]; disabled?: boolean })` con `MenuItem = { key: string; label: ReactNode; onSelect?: () => void; href?: string; disabled?: boolean }` da `@/components/ui` (usato dal Task 4). Item con `href` → `<a target="_blank" rel="noopener noreferrer">`; item con `onSelect` → `<button>`. Il menu si chiude su selezione, Escape e click fuori.
  - `TrackUpdate.archived?: boolean` (usato dal Task 5 via `updateTrack`).

- [ ] **Step 1: Setup worktree frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774/frontend
npm install
```

Atteso: install pulito da `package-lock.json`.

- [ ] **Step 2: Test store-links (failing)**

Creare `frontend/tests/store-links.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { STORES, storeQuery } from "@/lib/store-links";

describe("storeQuery", () => {
  it("unisce artista e titolo urlencoded", () => {
    expect(storeQuery("Marco Faraone", "Real Freak")).toBe("Marco%20Faraone%20Real%20Freak");
  });
  it("tollera artista o titolo mancanti", () => {
    expect(storeQuery(null, "Real Freak")).toBe("Real%20Freak");
    expect(storeQuery("Marco Faraone", null)).toBe("Marco%20Faraone");
  });
});

describe("STORES", () => {
  it("sono i 4 negozi della spec, nell'ordine", () => {
    expect(STORES.map((s) => s.key)).toEqual(["bandcamp", "beatport", "juno", "discogs"]);
  });
  it("generano gli URL di ricerca della spec", () => {
    const q = storeQuery("A", "B");
    const urls = Object.fromEntries(STORES.map((s) => [s.key, s.url(q)]));
    expect(urls.bandcamp).toBe("https://bandcamp.com/search?q=A%20B");
    expect(urls.beatport).toBe("https://www.beatport.com/search?q=A%20B");
    expect(urls.juno).toBe("https://www.junodownload.com/search/?q%5Ball%5D%5B%5D=A%20B");
    expect(urls.discogs).toBe("https://www.discogs.com/search/?q=A%20B&type=release");
  });
});
```

- [ ] **Step 3: Verificare che fallisca**

```bash
npx vitest run tests/store-links.test.ts
```

Atteso: FAIL (modulo `@/lib/store-links` inesistente).

- [ ] **Step 4: Implementare `lib/store-links.ts`**

```ts
// Link d'acquisto della wishlist: ricerche precompilate, si aprono in un'altra
// tab e l'acquisto avviene sul negozio. Niente API, niente chiavi (spec
// 2026-07-19): Cratory resta deterministico e offline-friendly.

export type StoreKey = "bandcamp" | "beatport" | "juno" | "discogs";

export const STORES: { key: StoreKey; label: string; url: (q: string) => string }[] = [
  { key: "bandcamp", label: "Bandcamp", url: (q) => `https://bandcamp.com/search?q=${q}` },
  { key: "beatport", label: "Beatport", url: (q) => `https://www.beatport.com/search?q=${q}` },
  { key: "juno", label: "Juno Download", url: (q) => `https://www.junodownload.com/search/?q%5Ball%5D%5B%5D=${q}` },
  { key: "discogs", label: "Discogs", url: (q) => `https://www.discogs.com/search/?q=${q}&type=release` },
];

export function storeQuery(artist: string | null, title: string | null): string {
  return encodeURIComponent([artist, title].filter(Boolean).join(" "));
}
```

- [ ] **Step 5: Verificare che passi**

```bash
npx vitest run tests/store-links.test.ts
```

Atteso: PASS.

- [ ] **Step 6: Test DropdownMenu (failing)**

Creare `frontend/tests/dropdown-menu.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DropdownMenu } from "@/components/ui";

afterEach(cleanup);

describe("DropdownMenu", () => {
  it("apre al click e chiude alla selezione", () => {
    const onSelect = vi.fn();
    render(<DropdownMenu label="Compra" items={[{ key: "a", label: "Azione", onSelect }]} />);
    expect(screen.queryByText("Azione")).toBeNull();
    fireEvent.click(screen.getByText("Compra"));
    fireEvent.click(screen.getByText("Azione"));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("gli item href sono link in nuova tab", () => {
    render(<DropdownMenu label="Compra" items={[{ key: "b", label: "Bandcamp", href: "https://bandcamp.com/search?q=x" }]} />);
    fireEvent.click(screen.getByText("Compra"));
    const a = screen.getByText("Bandcamp").closest("a");
    expect(a?.getAttribute("href")).toBe("https://bandcamp.com/search?q=x");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noopener");
  });

  it("chiude con Escape", () => {
    render(<DropdownMenu label="Menu" items={[{ key: "a", label: "Azione", onSelect: () => {} }]} />);
    fireEvent.click(screen.getByText("Menu"));
    expect(screen.getByText("Azione")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("Azione")).toBeNull();
  });

  it("disabled non apre", () => {
    render(<DropdownMenu label="Menu" disabled items={[{ key: "a", label: "Azione", onSelect: () => {} }]} />);
    fireEvent.click(screen.getByText("Menu"));
    expect(screen.queryByText("Azione")).toBeNull();
  });
});
```

- [ ] **Step 7: Verificare che fallisca**

```bash
npx vitest run tests/dropdown-menu.test.tsx
```

Atteso: FAIL (`DropdownMenu` non esportato).

- [ ] **Step 8: Implementare `DropdownMenu` in `components/ui.tsx`**

In coda al file (dopo `Alert`), riusando gli import già presenti nel file (`useState`, `useRef`, `useEffect`, `useId`, `cn`, tipi `Variant`/`Size` e classi `BTN_VARIANT`/`BTN_SIZE`):

```tsx
/* ------------------------------------------------------------ DropdownMenu */

export type MenuItem = {
  key: string;
  label: ReactNode;
  onSelect?: () => void;
  href?: string;          // alternativa a onSelect: link esterno in nuova tab
  disabled?: boolean;
};

export function DropdownMenu({ label, items, disabled, size = "sm", variant = "outline" }: {
  label: ReactNode;
  items: MenuItem[];
  disabled?: boolean;
  size?: Size;
  variant?: Variant;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  // Chiusura su click fuori ed Escape: listener globali solo quando aperto.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const itemClass = "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-muted hover:bg-elevated hover:text-fg disabled:opacity-50";

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={cn("inline-flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-50",
          BTN_VARIANT[variant], BTN_SIZE[size])}
      >
        {label}
      </button>
      {open && (
        <div id={menuId} role="menu"
          className="absolute right-0 top-full z-30 mt-1 min-w-40 border border-border-strong bg-surface py-1">
          {items.map((it) =>
            it.href ? (
              <a key={it.key} role="menuitem" href={it.href} target="_blank" rel="noopener noreferrer"
                className={itemClass} onClick={() => setOpen(false)}>
                {it.label}
              </a>
            ) : (
              <button key={it.key} type="button" role="menuitem" disabled={it.disabled}
                className={itemClass}
                onClick={() => { setOpen(false); it.onSelect?.(); }}>
                {it.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
```

Se `useRef`/`useEffect`/`useId` non sono già importati in testa a `ui.tsx`, aggiungerli all'import da `react`. Verificare le classi `BTN_VARIANT`/`BTN_SIZE` esistenti (`ui.tsx:40-49`) e lo stile del pannello sul `Combobox` (`ui.tsx:230~`): il menu deve essere coerente col DS (bordi netti, niente rounded se il DS non li usa).

- [ ] **Step 9: Aggiornare `TrackUpdate`**

In `frontend/lib/api/types.ts`, dentro `interface TrackUpdate` dopo `label`:

```ts
  archived?: boolean;
```

- [ ] **Step 10: Verificare test + lint**

```bash
npx vitest run tests/dropdown-menu.test.tsx tests/store-links.test.ts && npm run lint
```

Atteso: PASS, lint pulito.

- [ ] **Step 11: Commit**

```bash
git add frontend/lib/store-links.ts frontend/lib/api/types.ts frontend/components/ui.tsx frontend/tests/store-links.test.ts frontend/tests/dropdown-menu.test.tsx
git commit -m "feat(wishlist): fondamenta frontend — link negozi, DropdownMenu, archived nel TrackUpdate"
```

---

### Task 3: i18n — sezione `wishlist` + helper di stato

**Files:**
- Modify: `frontend/lib/i18n/en.ts` (nuova sezione `wishlist` dopo la sezione `downloads`; `nav.downloads` → "Wishlist")
- Modify: `frontend/lib/i18n/it.ts` (idem, stessa struttura)
- Create: `frontend/lib/wishlist-status.ts`
- Test: `frontend/tests/wishlist-status.test.ts` (nuovo)

**Interfaces:**
- Produces:
  - `wishlistStatus(t: { last_download_outcome: string | null }): WishlistStatus` con `WishlistStatus = "never" | "review" | "not_found" | "failed" | "downloaded_unlinked"` da `@/lib/wishlist-status` (usato da Task 4 e 5).
  - `statusTab(s: WishlistStatus): "never" | "review" | "not_found" | "failed"` — mappa `downloaded_unlinked` → `review` (spec: conta sotto "In review").
  - Chiavi `t.wishlist.*` e `t.nav.downloads` = "Wishlist" (usate da Task 4, 5, 6).

- [ ] **Step 1: Test wishlist-status (failing)**

Creare `frontend/tests/wishlist-status.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { statusTab, wishlistStatus } from "@/lib/wishlist-status";

describe("wishlistStatus", () => {
  it("mappa gli esiti download", () => {
    expect(wishlistStatus({ last_download_outcome: null })).toBe("never");
    expect(wishlistStatus({ last_download_outcome: "needs_review" })).toBe("review");
    expect(wishlistStatus({ last_download_outcome: "not_found" })).toBe("not_found");
    expect(wishlistStatus({ last_download_outcome: "failed" })).toBe("failed");
    // In wishlist has_local_file e' sempre false: un esito "downloaded" senza
    // file e' il caso limite della spec.
    expect(wishlistStatus({ last_download_outcome: "downloaded" })).toBe("downloaded_unlinked");
  });
  it("esiti sconosciuti non rompono: trattati come mai tentata", () => {
    expect(wishlistStatus({ last_download_outcome: "boh" })).toBe("never");
  });
});

describe("statusTab", () => {
  it("downloaded_unlinked conta sotto review", () => {
    expect(statusTab("downloaded_unlinked")).toBe("review");
    expect(statusTab("never")).toBe("never");
    expect(statusTab("not_found")).toBe("not_found");
    expect(statusTab("failed")).toBe("failed");
    expect(statusTab("review")).toBe("review");
  });
});
```

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/wishlist-status.test.ts
```

Atteso: FAIL (modulo inesistente).

- [ ] **Step 3: Implementare `lib/wishlist-status.ts`**

```ts
// Stato wishlist di una traccia non posseduta, derivato dall'ultimo esito
// download. "downloaded" qui significa "scaricata ma non collegata" (in
// wishlist has_local_file e' per definizione false): caso limite della spec,
// nel filtro conta sotto "review".

export type WishlistStatus = "never" | "review" | "not_found" | "failed" | "downloaded_unlinked";
export type WishlistTab = "never" | "review" | "not_found" | "failed";

export function wishlistStatus(t: { last_download_outcome: string | null }): WishlistStatus {
  switch (t.last_download_outcome) {
    case "needs_review": return "review";
    case "not_found": return "not_found";
    case "failed": return "failed";
    case "downloaded": return "downloaded_unlinked";
    default: return "never";
  }
}

export function statusTab(s: WishlistStatus): WishlistTab {
  return s === "downloaded_unlinked" ? "review" : s;
}
```

- [ ] **Step 4: Verificare che passi**

```bash
npx vitest run tests/wishlist-status.test.ts
```

Atteso: PASS.

- [ ] **Step 5: Chiavi i18n**

In `frontend/lib/i18n/en.ts`: cambiare `nav.downloads` da `"Downloads"` a `"Wishlist"`, e aggiungere dopo la sezione `downloads` (stesso livello):

```ts
  wishlist: {
    pageTitle: "Wishlist",
    filterAria: "Filter by download status",
    tabAll: "All",
    tabNever: "Never tried",
    tabReview: "In review",
    tabNotFound: "Not found",
    tabFailed: "Failed",
    searchPlaceholder: "Filter by artist or title…",
    playlistAllOption: "All playlists",
    showArchivedLabel: "Show archived",
    badgeNever: "never tried",
    badgeReview: "in review",
    badgeNotFound: "not found",
    badgeFailed: "failed",
    badgeDownloadedUnlinked: "downloaded, not linked",
    provenanceMore: (n: number) => `+${n}`,
    downloadButton: "Download",
    retryButton: "Retry",
    reviewButton: "Review",
    buyButton: "Buy",
    moreActionsAria: "More actions",
    linkFileButton: "Link file",
    clearOutcomeButton: "Clear outcome",
    archiveButton: "Archive",
    restoreButton: "Restore",
    archiveConfirm: (label: string) => `Archive “${label}”? It leaves the wishlist; you can restore it from “Show archived”.`,
    emptyTitle: "Wishlist is empty",
    emptyBody: "Every track you own is on disk. Import playlists or dig in Discovery to add leads.",
    emptyFilteredTitle: "No tracks with this filter",
    emptyFilteredBody: "Change status tab, playlist or search.",
    archivedEmptyTitle: "No archived tracks",
    archivedEmptyBody: "Tracks you archive from the wishlist will show up here.",
    soulseekHeading: "Free Soulseek search",
    soulseekToggle: "Search Soulseek manually",
    bulkHeading: "Bulk actions",
  },
```

In `frontend/lib/i18n/it.ts`: `nav.downloads` → `"Wishlist"`, e la stessa sezione:

```ts
  wishlist: {
    pageTitle: "Wishlist",
    filterAria: "Filtra per stato download",
    tabAll: "Tutte",
    tabNever: "Mai tentate",
    tabReview: "In review",
    tabNotFound: "Non trovate",
    tabFailed: "Fallite",
    searchPlaceholder: "Filtra per artista o titolo…",
    playlistAllOption: "Tutte le playlist",
    showArchivedLabel: "Mostra archiviate",
    badgeNever: "mai tentata",
    badgeReview: "in review",
    badgeNotFound: "non trovata",
    badgeFailed: "fallita",
    badgeDownloadedUnlinked: "scaricata, non collegata",
    provenanceMore: (n: number) => `+${n}`,
    downloadButton: "Scarica",
    retryButton: "Riprova",
    reviewButton: "Rivedi",
    buyButton: "Compra",
    moreActionsAria: "Altre azioni",
    linkFileButton: "Collega file",
    clearOutcomeButton: "Azzera esito",
    archiveButton: "Archivia",
    restoreButton: "Ripristina",
    archiveConfirm: (label: string) => `Archiviare «${label}»? Esce dalla wishlist; puoi ripristinarla da «Mostra archiviate».`,
    emptyTitle: "Wishlist vuota",
    emptyBody: "Tutte le tracce che possiedi sono su disco. Importa playlist o scava in Discovery per aggiungere lead.",
    emptyFilteredTitle: "Nessuna traccia con questo filtro",
    emptyFilteredBody: "Cambia tab di stato, playlist o ricerca.",
    archivedEmptyTitle: "Nessuna traccia archiviata",
    archivedEmptyBody: "Le tracce che archivi dalla wishlist compariranno qui.",
    soulseekHeading: "Ricerca Soulseek libera",
    soulseekToggle: "Cerca a mano su Soulseek",
    bulkHeading: "Azioni di gruppo",
  },
```

- [ ] **Step 6: Lint + typecheck**

```bash
npm run lint && npx tsc --noEmit
```

Atteso: pulito (se il progetto non ha `tsc --noEmit` funzionante, basta `npm run build` nel Task 6 — lint deve comunque passare).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/lib/wishlist-status.ts frontend/tests/wishlist-status.test.ts
git commit -m "feat(wishlist): stato wishlist derivato dall'esito download + copy i18n it/en"
```

---

### Task 4: Componente riga — `WishlistRow`

**Files:**
- Create: `frontend/components/wishlist-row.tsx`
- Test: `frontend/tests/wishlist-row.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `wishlistStatus` (Task 3), `STORES`/`storeQuery` (Task 2), `DropdownMenu` (Task 2), `Badge`/`Button` da `@/components/ui`, `trackLabel` e `type Track` da `@/lib/api`, `t.wishlist.*` (Task 3).
- Produces: `WishlistRow(props)` — riga completa di provenienza, badge, azione primaria contestuale, menu Compra e overflow. Props esatte:

```ts
export type WishlistRowProps = {
  track: Track;
  archived?: boolean;              // vista "mostra archiviate": solo Ripristina + Compra
  downloadsAvailable: boolean;     // slskd configurato e nessun job in corso
  onDownload: (t: Track) => void;  // auto-pick (mai tentata / riprova)
  onReview: (t: Track) => void;    // apre DownloadReviewModal
  onLinkFile: (t: Track) => void;  // apre LinkLocalFileModal
  onClearOutcome: (t: Track) => void;
  onArchive: (t: Track) => void;   // il conferma sta nella pagina
  onRestore: (t: Track) => void;
};
```

- [ ] **Step 1: Test (failing)**

Creare `frontend/tests/wishlist-row.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { WishlistRow } from "@/components/wishlist-row";
import type { Track } from "@/lib/api";

afterEach(cleanup);

// I18nProvider di default e' "it" (vedi lib/i18n/index.tsx): se il render dei
// test richiede il provider, avvolgere qui con lo stesso wrapper usato dagli
// altri test di pagina (cfr. tests/analysis-page.test.tsx).

const base = {
  id: 1, title: "Real Freak", artist: "Marco Faraone",
  playlists: [{ id: 7, name: "Techno Peak" }, { id: 9, name: "Scoperte" }],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
} as unknown as Track;

const noop = { onDownload: vi.fn(), onReview: vi.fn(), onLinkFile: vi.fn(), onClearOutcome: vi.fn(), onArchive: vi.fn(), onRestore: vi.fn() };

describe("WishlistRow", () => {
  it("mostra label, chip playlist e badge 'mai tentata'", () => {
    render(<WishlistRow track={base} downloadsAvailable {...noop} />);
    expect(screen.getByText("Marco Faraone — Real Freak")).toBeTruthy();
    expect(screen.getByText("Techno Peak").closest("a")?.getAttribute("href")).toBe("/playlists/7");
    expect(screen.getByText("Scoperte").closest("a")?.getAttribute("href")).toBe("/playlists/9");
    expect(screen.getByText("mai tentata")).toBeTruthy();
  });

  it("azione primaria contestuale: Scarica se mai tentata, Riprova se non trovata, Rivedi se in review", () => {
    const { rerender } = render(<WishlistRow track={base} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Scarica"));
    expect(noop.onDownload).toHaveBeenCalled();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "not_found" } as Track} downloadsAvailable {...noop} />);
    expect(screen.getByText("Riprova")).toBeTruthy();
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "needs_review" } as Track} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Rivedi"));
    expect(noop.onReview).toHaveBeenCalled();
  });

  it("scaricata-non-collegata: primaria = Collega file", () => {
    render(<WishlistRow track={{ ...base, last_download_outcome: "downloaded" } as Track} downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Collega file"));
    expect(noop.onLinkFile).toHaveBeenCalled();
  });

  it("downloadsAvailable=false disabilita solo il download, Compra resta attivo", () => {
    render(<WishlistRow track={base} downloadsAvailable={false} {...noop} />);
    expect((screen.getByText("Scarica").closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Compra"));
    expect(screen.getByText("Bandcamp").closest("a")?.getAttribute("href"))
      .toBe("https://bandcamp.com/search?q=Marco%20Faraone%20Real%20Freak");
  });

  it("vista archiviata: solo Ripristina e Compra", () => {
    render(<WishlistRow track={base} archived downloadsAvailable {...noop} />);
    fireEvent.click(screen.getByText("Ripristina"));
    expect(noop.onRestore).toHaveBeenCalled();
    expect(screen.queryByText("Scarica")).toBeNull();
  });
});
```

Nota per l'esecutore: se `useT()` richiede un provider, aprire `frontend/lib/i18n/index.tsx` e un test esistente di componente che usa i18n (es. `tests/analysis-page.test.tsx`) e replicare lo stesso wrapper nel `render`. Il default del provider è "it": i testi attesi sopra sono italiani.

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/wishlist-row.test.tsx
```

Atteso: FAIL (componente inesistente).

- [ ] **Step 3: Implementare `components/wishlist-row.tsx`**

```tsx
"use client";

import Link from "next/link";
import { Download as DownloadIcon, Link2, MoreHorizontal, RotateCcw, Search, ShoppingCart } from "lucide-react";
import { Badge, Button, DropdownMenu } from "@/components/ui";
import { STORES, storeQuery } from "@/lib/store-links";
import { wishlistStatus, type WishlistStatus } from "@/lib/wishlist-status";
import { trackLabel, type Track } from "@/lib/api";
import { useT } from "@/lib/i18n";

export type WishlistRowProps = {
  track: Track;
  archived?: boolean;
  downloadsAvailable: boolean;
  onDownload: (t: Track) => void;
  onReview: (t: Track) => void;
  onLinkFile: (t: Track) => void;
  onClearOutcome: (t: Track) => void;
  onArchive: (t: Track) => void;
  onRestore: (t: Track) => void;
};

const BADGE_TONE: Record<WishlistStatus, "warning" | "danger" | "neutral"> = {
  never: "neutral",
  review: "warning",
  not_found: "neutral",
  failed: "danger",
  downloaded_unlinked: "warning",
};

const MAX_CHIPS = 2;

export function WishlistRow({
  track, archived, downloadsAvailable,
  onDownload, onReview, onLinkFile, onClearOutcome, onArchive, onRestore,
}: WishlistRowProps) {
  const t = useT();
  const status = wishlistStatus(track);
  const BADGE_LABEL: Record<WishlistStatus, string> = {
    never: t.wishlist.badgeNever,
    review: t.wishlist.badgeReview,
    not_found: t.wishlist.badgeNotFound,
    failed: t.wishlist.badgeFailed,
    downloaded_unlinked: t.wishlist.badgeDownloadedUnlinked,
  };
  const detail = status === "failed"
    ? t.downloads.failedReason(track.last_download_reason)
    : track.last_download_reason;
  const chips = track.playlists.slice(0, MAX_CHIPS);
  const extra = track.playlists.length - chips.length;
  const q = storeQuery(track.artist, track.title);

  const primary = (() => {
    if (archived) return null;
    switch (status) {
      case "never":
        return (
          <Button size="sm" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <DownloadIcon size={13} /> {t.wishlist.downloadButton}
          </Button>
        );
      case "not_found":
      case "failed":
        return (
          <Button size="sm" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <RotateCcw size={13} /> {t.wishlist.retryButton}
          </Button>
        );
      case "review":
        return (
          <Button size="sm" onClick={() => onReview(track)}>
            <Search size={13} /> {t.wishlist.reviewButton}
          </Button>
        );
      case "downloaded_unlinked":
        return (
          <Button size="sm" onClick={() => onLinkFile(track)}>
            <Link2 size={13} /> {t.wishlist.linkFileButton}
          </Button>
        );
    }
  })();

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <a href={`/tracks/${track.id}`} className="block truncate hover:text-fg-strong">{trackLabel(track)}</a>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
          {chips.map((p) => (
            <Link key={p.id} href={`/playlists/${p.id}`}
              className="border border-border px-1.5 py-px text-[10px] uppercase tracking-wider text-muted hover:text-fg">
              {p.name}
            </Link>
          ))}
          {extra > 0 && (
            <span className="text-[10px] text-faint" title={track.playlists.slice(MAX_CHIPS).map((p) => p.name).join(", ")}>
              {t.wishlist.provenanceMore(extra)}
            </span>
          )}
          {detail && <span className="text-xs text-muted">{detail}</span>}
        </div>
      </div>
      <span className="flex shrink-0 flex-wrap items-center gap-2">
        <Badge tone={BADGE_TONE[status]}>{BADGE_LABEL[status]}</Badge>
        {archived ? (
          <Button size="sm" variant="outline" onClick={() => onRestore(track)}>
            <RotateCcw size={13} /> {t.wishlist.restoreButton}
          </Button>
        ) : primary}
        <DropdownMenu
          label={<><ShoppingCart size={13} /> {t.wishlist.buyButton}</>}
          items={STORES.map((s) => ({ key: s.key, label: s.label, href: s.url(q) }))}
        />
        {!archived && (
          <DropdownMenu
            label={<MoreHorizontal size={13} aria-label={t.wishlist.moreActionsAria} />}
            variant="ghost"
            items={[
              { key: "link", label: t.wishlist.linkFileButton, onSelect: () => onLinkFile(track) },
              { key: "clear", label: t.wishlist.clearOutcomeButton, disabled: status === "never", onSelect: () => onClearOutcome(track) },
              { key: "archive", label: t.wishlist.archiveButton, onSelect: () => onArchive(track) },
            ]}
          />
        )}
      </span>
    </li>
  );
}
```

- [ ] **Step 4: Verificare che passi + lint**

```bash
npx vitest run tests/wishlist-row.test.tsx && npm run lint
```

Atteso: PASS, lint pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/wishlist-row.tsx frontend/tests/wishlist-row.test.tsx
git commit -m "feat(wishlist): riga della wishlist — provenienza, badge esito, azione contestuale, menu Compra"
```

---

### Task 5: Pagina `/wishlist`

**Files:**
- Create: `frontend/app/wishlist/page.tsx`
- Test: verifica con lint + build (la copertura funzionale arriva da unit già fatti + e2e del Task 6; la pagina è orchestrazione)

**Interfaces:**
- Consumes: `WishlistRow` (Task 4), `wishlistStatus`/`statusTab` (Task 3), `updateTrack` con `archived` (Task 1+2), API esistenti: `apiGet`, `downloadTrackAuto`, `startPlaylistDownload`, `retryPending`, `ignoreDownload`, `searchDownloads`, `downloadManual`, `listImportedPlaylists`, `errText`, `trackLabel`; modali esistenti `DownloadReviewModal`, `LinkLocalFileModal`, `AutoLinkModal`, `ConfirmModal`; `useJobs`.
- Produces: rotta `/wishlist` funzionante (usata dal Task 6 per nav/redirect/e2e).

- [ ] **Step 1: Scrivere la pagina**

Creare `frontend/app/wishlist/page.tsx`. Struttura completa (stessi pattern di `app/downloads/page.tsx`, che resta il riferimento fino al Task 6):

```tsx
"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, ChevronRight, Download as DownloadIcon, Heart, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Button, Card, Checkbox, EmptyState, Input, Loading, Select } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { WishlistRow } from "@/components/wishlist-row";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { AutoLinkModal } from "@/components/auto-link-modal";
import { ConfirmModal } from "@/components/confirm-modal";
import {
  apiGet, downloadManual, downloadTrackAuto, errText, ignoreDownload, listImportedPlaylists,
  retryPending, searchDownloads, startPlaylistDownload, trackLabel, updateTrack,
  type DownloadCandidate, type Playlist, type Track,
} from "@/lib/api";
import { statusTab, wishlistStatus, type WishlistTab } from "@/lib/wishlist-status";
import { useT } from "@/lib/i18n";

type Tab = "all" | WishlistTab;
const TAB_KEYS: Tab[] = ["all", "never", "review", "not_found", "failed"];

function WishlistInner() {
  const t = useT();
  const TAB_LABEL: Record<Tab, string> = {
    all: t.wishlist.tabAll,
    never: t.wishlist.tabNever,
    review: t.wishlist.tabReview,
    not_found: t.wishlist.tabNotFound,
    failed: t.wishlist.tabFailed,
  };
  const { download: jobStatus, refresh } = useJobs();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Filtri persistiti nella query string (pattern library/downloads): stato
  // iniziale dall'URL, modifiche riflesse con router.replace + debounce.
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>(TAB_KEYS.includes(tabParam as Tab) ? (tabParam as Tab) : "all");
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [playlistFilter, setPlaylistFilter] = useState(searchParams.get("playlist") ?? "");
  const [showArchived, setShowArchived] = useState(searchParams.get("archived") === "1");

  const [items, setItems] = useState<Track[] | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [bulkPlaylist, setBulkPlaylist] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Ricerca Soulseek libera (sezione secondaria, collassata di default).
  const [slskOpen, setSlskOpen] = useState(false);
  const [slskQuery, setSlskQuery] = useState("");
  const [slskResults, setSlskResults] = useState<DownloadCandidate[] | null>(null);
  const [slskSearching, setSlskSearching] = useState(false);

  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [autoLink, setAutoLink] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<Track | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback((signal?: AbortSignal) => {
    // limit=0 = tutte (l'endpoint pagina solo se richiesto): filtri e contatori
    // sono client-side, oggi ~55 tracce. `archived=true` restituisce SOLO le
    // archiviate: il toggle sostituisce la vista, non la mescola.
    return apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      has_local_file: "false",
      archived: showArchived ? "true" : undefined,
      sort: "artist", order: "asc", limit: 0,
    }, { signal })
      .then((r) => { if (alive.current) { setItems(r.items); setError(null); } })
      .catch((e) => { if (e?.name !== "AbortError" && alive.current) setError(errText(e)); });
  }, [showArchived]);

  // Ricarica quando il job produce esiti (processed cambia durante il run).
  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load, jobStatus?.status, jobStatus?.processed]);

  useEffect(() => {
    listImportedPlaylists().then((p) => alive.current && setPlaylists(p)).catch(() => undefined);
  }, []);

  // Stato -> URL (replace + debounce, default fuori dall'URL).
  useEffect(() => {
    const params = new URLSearchParams();
    if (tab !== "all") params.set("tab", tab);
    if (query) params.set("q", query);
    if (playlistFilter) params.set("playlist", playlistFilter);
    if (showArchived) params.set("archived", "1");
    const next = params.toString();
    if (next === searchParams.toString()) return;
    const timer = setTimeout(() => {
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [tab, query, playlistFilter, showArchived, pathname, router, searchParams]);

  const available = jobStatus?.available ?? true;
  const running = jobStatus?.status === "running";
  const downloadsAvailable = available && !running;

  // Filtro playlist: opzioni derivate dalle tracce (solo playlist rappresentate).
  const playlistOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const tr of items ?? []) for (const p of tr.playlists) seen.set(p.id, p.name);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [items]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((tr) => {
      if (tab !== "all" && statusTab(wishlistStatus(tr)) !== tab) return false;
      if (playlistFilter && !tr.playlists.some((p) => String(p.id) === playlistFilter)) return false;
      if (q && !`${tr.artist ?? ""} ${tr.title ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [items, tab, playlistFilter, query]);

  const count = useCallback((k: Tab) => (items ?? []).filter(
    (tr) => k === "all" || statusTab(wishlistStatus(tr)) === k).length, [items]);

  const act = async (fn: () => Promise<unknown>, after?: () => void) => {
    setError(null);
    try { await fn(); after?.(); } catch (e) { setError(errText(e)); }
  };
  const onDownload = (tr: Track) => act(() => downloadTrackAuto(tr.id), refresh);
  const onClearOutcome = (tr: Track) => act(() => ignoreDownload(tr.id), () => load());
  const onArchive = (tr: Track) => act(() => updateTrack(tr.id, { archived: true }), () => load());
  const onRestore = (tr: Track) => act(() => updateTrack(tr.id, { archived: false }), () => load());
  const startBulk = () => bulkPlaylist && act(() => startPlaylistDownload(Number(bulkPlaylist)), refresh);
  const retryAll = () => act(() => retryPending(), refresh);
  const runSlskSearch = async () => {
    const q = slskQuery.trim();
    if (!q) return;
    setSlskSearching(true); setError(null); setSlskResults(null);
    try { setSlskResults(await searchDownloads(q)); }
    catch (e) { setError(errText(e)); }
    finally { setSlskSearching(false); }
  };
  const grab = (c: DownloadCandidate) => act(() => downloadManual(c), refresh);

  return (
    <PageLayout title={t.wishlist.pageTitle} meta={items?.length || undefined}>
      <div className="space-y-6">
        {!available && <Alert tone="info">{t.downloads.notConfigured}</Alert>}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* Azioni di gruppo */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.wishlist.bulkHeading}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={bulkPlaylist} onChange={(e) => setBulkPlaylist(e.target.value)} disabled={!downloadsAvailable}>
              <option value="">{t.downloads.choosePlaylistOption}</option>
              {playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Button onClick={startBulk} disabled={!downloadsAvailable || !bulkPlaylist}>
              <DownloadIcon size={14} /> {t.downloads.downloadPlaylistButton}
            </Button>
            <Button variant="outline" onClick={retryAll} disabled={!downloadsAvailable}>
              <DownloadIcon size={13} /> {t.downloads.retryAllButton}
            </Button>
            <Button variant="outline" onClick={() => setAutoLink(true)}>
              <Link2 size={13} /> {t.downloads.linkAllButton}
            </Button>
          </div>
        </section>

        {/* Filtri */}
        <section>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label={t.wishlist.filterAria}>
              {TAB_KEYS.map((k) => (
                <Button key={k} size="sm" role="tab" aria-selected={tab === k}
                  variant={tab === k ? "primary" : "outline"} onClick={() => setTab(k)}>
                  {TAB_LABEL[k]} ({count(k)})
                </Button>
              ))}
            </div>
            <Input className="h-8 w-56" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={t.wishlist.searchPlaceholder} />
            <Select className="h-8" value={playlistFilter} onChange={(e) => setPlaylistFilter(e.target.value)}>
              <option value="">{t.wishlist.playlistAllOption}</option>
              {playlistOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </Select>
            <Checkbox label={t.wishlist.showArchivedLabel} checked={showArchived}
              onChange={(v) => { setShowArchived(v); setItems(null); }} />
          </div>

          {items === null && <Loading />}
          {items !== null && rows.length === 0 && (
            <EmptyState icon={<Heart size={28} />} title={
              showArchived ? t.wishlist.archivedEmptyTitle
                : items.length === 0 ? t.wishlist.emptyTitle : t.wishlist.emptyFilteredTitle
            }>
              {showArchived ? t.wishlist.archivedEmptyBody
                : items.length === 0 ? t.wishlist.emptyBody : t.wishlist.emptyFilteredBody}
            </EmptyState>
          )}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((tr) => (
                  <WishlistRow key={tr.id} track={tr} archived={showArchived}
                    downloadsAvailable={downloadsAvailable}
                    onDownload={onDownload}
                    onReview={(x) => setReview({ track_id: x.id, artist: x.artist, title: x.title })}
                    onLinkFile={(x) => setLinking({ id: x.id, artist: x.artist, title: x.title })}
                    onClearOutcome={onClearOutcome}
                    onArchive={setConfirmArchive}
                    onRestore={onRestore} />
                ))}
              </ul>
            </Card>
          )}
        </section>

        {/* Ricerca Soulseek libera (secondaria, collassata) */}
        <section>
          <button type="button" onClick={() => setSlskOpen((v) => !v)}
            className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted hover:text-fg">
            {slskOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />} {t.wishlist.soulseekHeading}
          </button>
          {slskOpen && (
            <div className="mt-2">
              <div className="flex flex-wrap items-center gap-2">
                <Input value={slskQuery} onChange={(e) => setSlskQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") runSlskSearch(); }}
                  placeholder={t.downloads.searchPlaceholder} disabled={!available} />
                <Button variant="outline" onClick={runSlskSearch} disabled={!available || slskSearching || !slskQuery.trim()}>
                  <Search size={14} /> {t.downloads.searchButton}
                </Button>
              </div>
              {slskSearching && <Loading label={t.downloads.searchingLabel} />}
              {slskResults && slskResults.length === 0 && !slskSearching && (
                <p className="mt-2 text-sm text-faint">{t.downloads.noSearchResults(slskQuery)}</p>
              )}
              {slskResults && slskResults.length > 0 && (
                <ul className="mt-3 divide-y divide-border border border-border">
                  {slskResults.slice(0, 40).map((c, i) => (
                    <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-3 px-3 py-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                        <div className="text-xs text-faint">
                          {c.format?.toUpperCase()}{c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
                        </div>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => grab(c)} disabled={running}>
                        <DownloadIcon size={13} /> {t.downloads.downloadButton}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      </div>

      <DownloadReviewModal target={review} onClose={() => setReview(null)}
        onPicked={() => { refresh(); setReview(null); load(); }} />
      <LinkLocalFileModal target={linking} onClose={() => setLinking(null)}
        onLinked={() => { setLinking(null); load(); }} />
      <AutoLinkModal open={autoLink} onClose={() => setAutoLink(false)} onLinked={() => load()} />
      <ConfirmModal open={confirmArchive !== null}
        message={confirmArchive ? t.wishlist.archiveConfirm(trackLabel(confirmArchive)) : ""}
        onConfirm={() => { const tr = confirmArchive; setConfirmArchive(null); if (tr) onArchive(tr); }}
        onClose={() => setConfirmArchive(null)} />
    </PageLayout>
  );
}

// useSearchParams richiede un boundary Suspense sulle pagine statiche (Next 16),
// stesso pattern di library/downloads/set-builder.
export default function WishlistPage() {
  return <Suspense><WishlistInner /></Suspense>;
}
```

Adattamenti che l'esecutore deve verificare sul codice reale (nomi presi da `app/downloads/page.tsx`, ricontrollare le firme):
- `useJobs()` restituisce `{ download, refresh }` con `download.available/status/processed` (`components/jobs-provider.tsx`).
- `Checkbox` ha firma `{ label, checked, onChange, disabled }` (`components/ui.tsx:258`): controllare se `onChange` passa il boolean o l'evento e adeguare.
- `PageLayout` accetta `title` e `meta` (vedi uso in `app/downloads/page.tsx:145`).

- [ ] **Step 2: Lint + unit + build**

```bash
npm run lint && npm run test:unit && npm run build
```

Atteso: tutto verde. La build compila la nuova rotta `/wishlist`.

- [ ] **Step 3: Verifica manuale rapida (dev)**

Avviare backend e frontend dev (o usare i server già attivi), aprire `http://localhost:3000/wishlist` e verificare: lista popolata (55 tracce reali), tab con contatori coerenti (46 non trovate, 8 mai tentate, 1 in review da `downloaded` senza file), chip playlist cliccabili, menu Compra che apre il negozio in nuova tab.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/wishlist/page.tsx
git commit -m "feat(wishlist): pagina /wishlist — tutte le non possedute con esito, provenienza, bulk e Soulseek secondario"
```

---

### Task 6: Routing — nav, redirect, rimozione `/downloads`

**Files:**
- Modify: `frontend/components/index-nav.tsx:29` (href) e `:109` (badge)
- Modify: `frontend/next.config.ts` (redirect)
- Delete: `frontend/app/downloads/page.tsx`
- Modify: `frontend/e2e/smoke.spec.ts` (ROUTES)

**Interfaces:**
- Consumes: rotta `/wishlist` (Task 5), label `t.nav.downloads` = "Wishlist" (Task 3).
- Produces: `/downloads` → 307 verso `/wishlist`; nav aggiornata. Nessun altro task dipende da questo.

- [ ] **Step 1: Nav**

In `frontend/components/index-nav.tsx`:
- riga 29: `{ href: "/downloads", label: t.nav.downloads }` → `{ href: "/wishlist", label: t.nav.downloads }` (la label è già "Wishlist" dal Task 3; la chiave i18n resta `nav.downloads` per minimizzare il churn).
- riga ~109: `href === "/downloads"` → `href === "/wishlist"` (il badge col conteggio "da sistemare" resta su `downloadPending()`).

- [ ] **Step 2: Redirect**

In `frontend/next.config.ts`, dentro `nextConfig` accanto a `rewrites`:

```ts
  async redirects() {
    return [
      // La sezione Download e' diventata Wishlist (spec 2026-07-19): i vecchi
      // link/bookmark non si rompono. permanent:false — e' un rename interno.
      { source: "/downloads", destination: "/wishlist", permanent: false },
    ];
  },
```

Next 16: se la build segnala che `redirects` non è più supportato in questa forma, consultare `frontend/node_modules/next/dist/docs/` (vedi `frontend/CLAUDE.md`) e usare la forma documentata lì.

- [ ] **Step 3: Rimuovere la vecchia pagina**

```bash
git rm frontend/app/downloads/page.tsx
```

Verificare che nessun altro file importi da `app/downloads`:

```bash
grep -rn "app/downloads\|\"/downloads\"" frontend --include="*.tsx" --include="*.ts" -l | grep -v node_modules
```

Atteso: solo `e2e/smoke.spec.ts` (sistemato allo step 4). Gli usi di `href={\`/tracks/...\`}` con query `?from=` verso `/downloads` (se esistono, cercare `from=%2Fdownloads` o simili in `app/tracks/`) vanno aggiornati a `/wishlist`.

- [ ] **Step 4: E2E smoke**

In `frontend/e2e/smoke.spec.ts`, nella lista `ROUTES`, sostituire:

```ts
  { path: "/downloads", title: null },
```

con:

```ts
  { path: "/wishlist", title: "Wishlist" },
```

- [ ] **Step 5: Lint + build + e2e**

```bash
npm run lint && npm run build && npm run test:e2e
```

Atteso: tutto verde (l'e2e avvia i suoi server su 8211/3211 con DB pulito).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/index-nav.tsx frontend/next.config.ts frontend/e2e/smoke.spec.ts
git commit -m "feat(wishlist): nav e redirect — /downloads diventa /wishlist, vecchia pagina rimossa"
```

(Il `git rm` dello step 3 è già in staging.)

---

### Task 7: E2E wishlist + documentazione

**Files:**
- Create: `frontend/e2e/wishlist.spec.ts`
- Modify: `docs/API.md` (sezione del `PATCH /api/tracks/{id}`)
- Modify: `docs/ROADMAP.md` (stato)
- Modify: `PROGRESS.md` (diario)

**Interfaces:**
- Consumes: tutto quanto sopra. Non produce interfacce.

- [ ] **Step 1: E2E dedicato**

Creare `frontend/e2e/wishlist.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

// Wishlist (spec 2026-07-19): pagina delle tracce non possedute. Con DB vuoto
// verifichiamo montaggio, tab di stato e redirect dalla vecchia rotta.

test("monta con empty state e tab di stato", async ({ page }) => {
  await page.goto("/wishlist");
  await expect(page.getByRole("heading", { name: "Wishlist" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Tutte/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Mai tentate/ })).toBeVisible();
});

test("/downloads reindirizza a /wishlist", async ({ page }) => {
  await page.goto("/downloads");
  await expect(page).toHaveURL(/\/wishlist$/);
});
```

Nota: la lingua di default dell'app è l'italiano (provider i18n): i nomi dei tab sono quelli di `it.ts`. Se l'e2e gira in inglese (controllare come `smoke.spec.ts` gestisce la lingua — non la gestisce, quindi vale il default), usare i testi italiani come sopra.

- [ ] **Step 2: Eseguire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774/frontend
npm run test:e2e
```

Atteso: PASS (smoke + wishlist).

- [ ] **Step 3: Documentazione**

- `docs/API.md`: nella sezione del `PATCH /api/tracks/{track_id}`, aggiungere il campo:

```markdown
- `archived` (bool, opzionale): archivia/ripristina la traccia dalla wishlist.
  A differenza degli altri campi, `null` NON azzera: vale come "invariato"
  (bool NOT NULL). L'indicizzazione libreria continua a vincere: il possesso
  su disco riporta `archived=false`.
```

- `docs/API.md`: se esiste una sezione sulla pagina Download/downloads router, aggiornare il riferimento alla UI: la pagina è `/wishlist` (il router `/api/downloads/*` non cambia).
- `docs/ROADMAP.md`: nella sezione stato/decisioni, una riga: rifacimento Wishlist completato (2026-07-19) — `/downloads` → `/wishlist`, tutte le non possedute con esito download, provenienza playlist, acquisto via link (Bandcamp/Beatport/Juno/Discogs), archiviazione reversibile via PATCH.
- `PROGRESS.md`: voce di diario in testa col formato esistente (data, cosa è stato fatto, file toccati principali, come riprendere).

- [ ] **Step 4: Suite completa finale**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-download-redesign-2ac774/backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests
cd ../frontend
npm run lint && npm run test:unit && npm run build && npm run test:e2e
```

Atteso: tutto verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/wishlist.spec.ts docs/API.md docs/ROADMAP.md PROGRESS.md
git commit -m "test(wishlist): e2e redirect e montaggio + docs aggiornate (API, roadmap, diario)"
```
