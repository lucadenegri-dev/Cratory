# Settings unificata post-fusione — Design

**Data:** 2026-08-13
**Stato:** approvato

## Obiettivo

Dopo la fusione F1–F6 la pagina `/settings` è confusionaria e ridondante: due
liste di provider quasi identiche, due chiavi AI documentate, slskd presente in
tre punti, card sciolte fuori da ogni raggruppamento. Questo design la riporta a
una pagina sola, coerente con "un prodotto solo": un endpoint servizi unico, una
semantica di stato unica, quattro gruppi logici.

## Stato attuale (misurato, 2026-08-13)

La pagina `frontend/app/settings/page.tsx` monta in sequenza 7 blocchi:

1. Lingua (switcher IT/EN).
2. "Servizi" da `GET /api/services/status`: Spotify, Anthropic (`AI_API_KEY`),
   Discogs, slskd.
3. `ConfigCard`: `library_root`, `archive_root`, `slskd_download_dir`,
   `slskd_url`, `slskd_config_path` + toggle `share_library`.
4. `LibraryIndexCard`: indicizzazione della libreria.
5. `SoundCloudCard`: username + stato yt-dlp (card sciolta, fuori dalla lista
   servizi).
6. `SoulseekCard`: connect/disconnect slskd con polling di transizione (terza
   apparizione di slskd nella pagina).
7. `OrganizeSection`: template di rinomina **più** una seconda lista provider da
   `GET /api/organize/providers`: MusicBrainz, Discogs, AcoustID, Anthropic
   (`ANTHROPIC_API_KEY`).

Ridondanze concrete:

- **Discogs e Anthropic compaiono due volte**, con descrizioni diverse.
- **Due chiavi AI reali nel backend**: `AI_API_KEY` (config.py → Set Agent,
  `integrations/llm.py`) e `ANTHROPIC_API_KEY` (letta da `os.environ` in
  `organize/services/ai_tags.py`).
- **Semantica di stato invertita** tra le due liste: in Organize `connected`
  significa "funziona senza chiave" e `configured` "token presente"; nella lista
  Cratory è il contrario.
- **slskd in tre punti**: voce lista, card dedicata, campi in ConfigCard.

## Design

### 1. Backend: un solo endpoint servizi

`GET /api/services/status` diventa l'unica fonte e restituisce 7 voci:
**Spotify, Anthropic, Discogs, MusicBrainz, AcoustID, slskd, SoundCloud.**

- MusicBrainz e AcoustID migrano da `/api/organize/providers`.
- Discogs e Anthropic diventano voci uniche, con descrizione che copre entrambi
  gli usi (Discovery + metadati Organize; Set Agent + tag AI).
- SoundCloud entra in lista (configured = yt-dlp disponibile; il dettaglio
  riporta versione yt-dlp e username corrente).

Semantica di stato unica per tutte le voci:

- `configured` (bool): la configurazione **necessaria** è presente. Per servizi
  senza chiave obbligatoria (Discogs, MusicBrainz) è `true` di suo.
- `connected` (bool | null): stato vivo di sessione dove esiste (OAuth Spotify,
  login slskd); `null` dove il concetto non si applica.
- `optional_env` (list[str], nuovo): variabili facoltative (es. `DISCOGS_TOKEN`),
  rese in UI come "consigliata" — non più come servizio non configurato.
- `env` resta l'elenco delle variabili necessarie.

`GET /api/organize/providers` viene **rimosso**: router `providers.py`, schema
`ProviderInfo`, client `listProviders`. L'azione fingerprint (`runFingerprint`,
`POST /api/organize/fingerprint`) resta dov'è, sotto `/api/organize/*`.

### 2. Backend: chiave AI unica

- `config.py`: `ai_api_key` legge `ANTHROPIC_API_KEY` con fallback su
  `AI_API_KEY` (retrocompatibilità: gli `.env` esistenti continuano a
  funzionare).
- `organize/services/ai_tags.py`: `is_configured()` smette di leggere
  `os.environ` e usa lo stesso setting; anche il client interno usa la chiave
  dal setting.
- I messaggi d'errore che citano `AI_API_KEY` (`routers/sets.py`,
  `integrations/llm.py`) citano `ANTHROPIC_API_KEY`.
- La UI documenta solo `ANTHROPIC_API_KEY` (+ `AI_MODEL`).

### 3. Frontend: pagina a 4 gruppi

```
GENERALE             lingua (invariato)
PERCORSI E LIBRERIA  ConfigCard + indicizzazione fuse in un blocco unico
                     (library_root e "Indicizza ora" adiacenti;
                      share_library resta qui)
SERVIZI ESTERNI      lista unificata, 7 righe, azioni inline:
                       · Spotify    → Connetti/Riconnetti + redirect URI
                       · slskd      → Connetti/Disconnetti + stato login
                       · SoundCloud → campo username + salva
                       · AcoustID   → "Identifica ora" + esito fingerprint
ORGANIZE             solo template di rinomina/cartelle con anteprima
```

- `SoulseekCard` e `SoundCloudCard` spariscono come blocchi autonomi; la loro
  logica (compreso il polling di transizione slskd) si sposta nelle righe della
  lista.
- `OrganizeSection` perde `ProviderList` e `StatusBadge`.
- `statusLabel` diventa l'unica funzione di resa dello stato, estesa per
  `optional_env` ("token consigliato").

### 4. Copy, i18n e documentazione

- Dizionari IT/EN: si eliminano le voci provider duplicate in
  `t.organize.settings` (providersMeta, statusConnected/Configured/Missing, …);
  la semantica nuova ("Attiva", "Da collegare", "Token consigliato",
  "Non configurata") vive solo in `t.settings`.
- `docs/API.md`: endpoint servizi esteso documentato, `/api/organize/providers`
  rimosso.
- `README.md`: `ANTHROPIC_API_KEY` al posto di `AI_API_KEY` nell'esempio `.env`.
- `docs/ROADMAP.md` / `PROGRESS.md` aggiornati secondo l'abitudine del repo.

### 5. Errori e test

- Degrado come oggi: backend giù → un solo alert in testa alla pagina; le righe
  con azioni gestiscono errori localmente.
- Backend (TDD): i test di `tests/organize/test_providers_api.py` migrano su
  `/api/services/status` — voci unificate, semantica di stato, `optional_env`,
  fallback `AI_API_KEY` → `ANTHROPIC_API_KEY` (precedenza a
  `ANTHROPIC_API_KEY` se entrambe presenti).
- Frontend: `tests/settings-unica.test.tsx` si aggiorna alla nuova struttura
  (mock del solo endpoint servizi). Ogni asserzione va provata rompendo il
  codice (regola anti test-vacui).
- Verifica finale: `pytest`, `npm run lint`, `npm run build`, controllo visivo
  della pagina nel browser.

## Fuori scope

- Nessun cambiamento alle pagine operative di Organize (issues, duplicates,
  plan, history, files).
- Nessun cambiamento al comportamento dei servizi stessi (solo al loro stato
  riportato e alla loro presentazione).
- Nessuna migrazione dati: la convergenza della chiave AI è solo lettura di
  variabili d'ambiente con fallback.
