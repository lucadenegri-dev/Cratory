# ③ Shell Tauri e sidecar Python — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un `Cratory.app` che si apre con un doppio clic e funziona senza che sulla macchina sia installato nient'altro.

**Architecture:** Un guscio Tauri v2 in `src-tauri/` avvia il backend Python come processo figlio, aspetta che risponda in HTTP e poi mostra il frontend statico. Interprete, dipendenze e binari esterni viaggiano dentro il bundle, assemblati da uno script di build che riusa il manifest già esistente invece di duplicarne URL e hash.

**Tech Stack:** Tauri v2 (Rust), `@tauri-apps/cli` come devDependency npm, CPython 3.11 rilocabile (python-build-standalone), `otool`/`install_name_tool`/`codesign` degli Xcode Command Line Tools.

Spec: `docs/superpowers/specs/2026-08-22-tauri-shell-sidecar-design.md`.
Contesto d'insieme: `docs/superpowers/specs/2026-08-22-tauri-decomposizione-design.md`.

## Global Constraints

- **Non scrivere Rust a memoria.** Tauri v2 è recente e la sua API cambia fra minor. Ogni volta che serve una chiamata Tauri (percorso delle risorse, ciclo di vita, eventi di finestra), **leggila dalla documentazione della versione realmente installata** — `npx tauri --version` e i doc del crate — invece di ricordarla. Una firma inventata che compila per caso è peggio di una domanda.
- **Porta 8000 fissa.** `spotify_redirect_uri` è registrata su Spotify con quel numero. Se la porta è occupata si fallisce con un messaggio comprensibile; **non** si cerca la prima libera.
- **Mai `bin/uvicorn`.** Gli script in `bin/` di un CPython rilocabile portano dentro lo shebang il percorso assoluto della macchina di build. Si invoca sempre `python3 -m uvicorn`.
- **Non duplicare il manifest.** URL, versioni e SHA256 di `fpcalc` e `slskd` stanno in `backend/app/services/binary_manifest.py` e si leggono da lì con `entry_for(key)`. Copiarli nello script di build creerebbe due verità che divergono al primo bump.
- **`NEXT_PUBLIC_API_URL` è incorporata a build time**, non letta a runtime: va passata al comando di build del frontend, non all'ambiente del guscio.
- **La firma ad-hoc va applicata dopo `install_name_tool`**, che invalida la firma di ogni file che tocca.
- **Nessuna dipendenza Python nuova.** `backend/requirements.txt` non si tocca.
- **Lingua:** commenti e docstring in italiano; `docs/*.md` e `PROGRESS.md` in inglese.
- **Il backend non cambia.** ① e ② hanno già preparato i tre seam (`CRATORY_DATA_DIR`, `CRATORY_BIN_DIR`, `CRATORY_VERSION`). Se durante il ③ sembra necessario modificare `backend/app/`, fermarsi e segnalarlo: quasi certamente significa che si sta aggirando un seam invece di usarlo.

## Dati verificati, da usare invece di riscoprirli

- `binary_manifest.platform_tag()` qui vale `darwin-arm64`.
- `entry_for("fpcalc")` → v1.6.1, archivio `tar.gz`, `member=fpcalc`, `layout=single`, `version_flag=-version`.
- `entry_for("slskd")` → v0.26.0, archivio `zip`, `member=slskd`, `layout=bundle`, `version_flag=--version`.
- `entry_for("ffmpeg")` → **`None`**: nessuna build upstream arm64 con checksum. Da qui la rilocazione del Task 3.
- Il CPython rilocabile pinnato dallo spike: `cpython-3.11.16+20260814-aarch64-apple-darwin-install_only.tar.gz` dalle release di `astral-sh/python-build-standalone`, tag `20260814`. 299 MB installato, **195 MB potato**, 71 compresso.
- ffmpeg di Homebrew qui è la **9.0.1**, arm64, con **19 dylib** in chiusura transitiva, 37 MB una volta rilocato.
- `backend/app` pesa 3.2 MB su 162 file `.py`.

## Struttura dei file

| File | Responsabilità | Task |
|---|---|---|
| `src-tauri/` (Cargo, `tauri.conf.json`, `src/main.rs`) | Il guscio nativo | 1, 4 |
| `frontend/package.json` | `@tauri-apps/cli` come devDependency e gli script | 1 |
| `src-tauri/scripts/costruisci_runtime.py` | Scarica CPython, installa i requirements, pota, verifica | 2 |
| `src-tauri/scripts/costruisci_binari.py` | ffmpeg rilocato + fpcalc e slskd dal manifest | 3 |
| `src-tauri/scripts/assembla.py` | Orchestrazione: frontend, backend, runtime, binari | 5 |
| `.gitignore` | Gli artefatti di build non entrano in git | 1 |

---

### Task 1: Lo scaffold e la finestra

**Files:**
- Create: `src-tauri/` (scaffold completo), `src-tauri/.gitignore`
- Modify: `frontend/package.json` (devDependency + script), `.gitignore` alla radice

**Interfaces:**
- Consumes: l'export statico del ②.
- Produces: `npm run tauri:dev` apre una finestra; `src-tauri/tauri.conf.json` con `frontendDist` che punta a `frontend/out`.

- [ ] **Step 1: Installare la CLI e verificare la versione reale**

```bash
cd frontend && npm install --save-dev @tauri-apps/cli && npx tauri --version
```

Annotare la versione stampata: **tutta l'API Rust dei task successivi va letta dalla documentazione di quella versione**, non dalla memoria.

- [ ] **Step 2: Generare lo scaffold**

Dalla radice del repository, generare `src-tauri/` con `npx tauri init` (dalla cartella `frontend/`, indicandogli `../src-tauri` come destinazione se lo chiede). Rispondere in modo che:

- il nome dell'app sia `Cratory`;
- `frontendDist` punti alla cartella dell'export statico, cioè `../frontend/out`;
- **non** ci sia un `beforeDevCommand`/`beforeBuildCommand` che lanci `next dev`: il frontend qui è statico, e un dev server avviato di nascosto confonderebbe le verifiche dei task successivi.

Se `tauri init` non offre queste scelte, correggere `src-tauri/tauri.conf.json` a mano dopo.

- [ ] **Step 3: Ignorare gli artefatti**

`src-tauri/target/` (build Rust, molto pesante) e `frontend/out/` non devono entrare in git. Verificare:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805
git status --porcelain | grep -E "src-tauri/target|frontend/out" && echo "DA IGNORARE" || echo "gia' ignorati"
```

Se compaiono, aggiungerli al `.gitignore` opportuno.

- [ ] **Step 4: Aggiungere gli script npm**

In `frontend/package.json`, sotto `scripts`:

```json
    "tauri": "tauri",
    "tauri:dev": "tauri dev",
    "tauri:build": "tauri build"
```

- [ ] **Step 5: Costruire il frontend statico e aprire la finestra**

```bash
cd frontend
CRATORY_STATIC_EXPORT=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build
npm run tauri:dev
```

Atteso: si apre una finestra nativa con l'interfaccia di Cratory. **Il backend non è ancora avviato dal guscio**, quindi le chiamate `/api/*` falliranno: è previsto, lo risolve il Task 4. Quello che deve funzionare qui è la finestra e il caricamento dei file statici.

Riportare cosa si è visto davvero. Se la finestra resta bianca, dire cosa c'è nella console del webview (in `tauri dev` si apre col menu contestuale o coi devtools) invece di tirare a indovinare.

- [ ] **Step 6: Commit**

```bash
git add -A src-tauri frontend/package.json frontend/package-lock.json .gitignore
git commit -m "feat(tauri): scaffold del guscio e finestra sul frontend statico

Il backend non e' ancora avviato dal guscio: qui si prova che la finestra si
apre e che i file statici dell'export si caricano."
```

---

### Task 2: Il runtime Python

**Files:**
- Create: `src-tauri/scripts/costruisci_runtime.py`

**Interfaces:**
- Consumes: `backend/requirements.txt`.
- Produces: `costruisci_runtime.py <destinazione>` che lascia in `<destinazione>/python/` un CPython funzionante e potato. Il Task 5 lo chiama.

**Perché uno script e non istruzioni a mano.** Va rifatto a ogni bump di dipendenza, e un passo dimenticato produce un bundle che si apre e poi fallisce su una funzione sola. Deve essere ripetibile e deve verificarsi da solo.

- [ ] **Step 1: Scrivere lo script**

Creare `src-tauri/scripts/costruisci_runtime.py`. Deve, in ordine:

1. Scaricare `https://github.com/astral-sh/python-build-standalone/releases/download/20260814/cpython-3.11.16%2B20260814-aarch64-apple-darwin-install_only.tar.gz` in una cartella temporanea.
2. Estrarlo in `<destinazione>/python`.
3. Installarci dentro `backend/requirements.txt` con `<destinazione>/python/bin/python3 -m pip install -r ...`.
4. Potare: `pip`, `setuptools`, `pkg_resources`, `pytest`, `_pytest`, `pygments`, ogni `__pycache__`, `lib/python3.11/test`, `idlelib`, `tkinter`, `lib2to3`, i `*.dist-info`, e `share/` e `include/`.
5. **Verificare eseguendo**, non ispezionando: lanciare `<destinazione>/python/bin/python3 -c "import essentia.standard, fastapi, uvicorn, yt_dlp, shazamio, mutagen, PIL, acoustid"` e fallire con un errore leggibile se non passa.
6. Stampare la dimensione finale.

Lo script è **idempotente**: rilanciarlo su una destinazione già popolata deve rifare tutto da zero, non accumulare.

Pinnare URL e SHA256 del runtime **in cima allo script, come costanti nominate**, e verificare l'hash dopo lo scaricamento — stessa disciplina di `binary_manifest`: un hash letto al momento verrebbe dalla stessa fonte che un rilascio compromesso controllerebbe.

- [ ] **Step 2: Eseguirlo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805
python3 src-tauri/scripts/costruisci_runtime.py /tmp/cratory-runtime-prova
```

Atteso: finisce senza errori e stampa una dimensione **intorno ai 195 MB**. Se è molto sopra, la potatura non ha funzionato; se molto sotto, ha tolto troppo e il passo 5 dovrebbe averlo già rilevato.

- [ ] **Step 3: La prova che conta — spostarlo**

```bash
mkdir -p /tmp/cratory-altrove && cp -R /tmp/cratory-runtime-prova/python /tmp/cratory-altrove/
env -i PATH=/usr/bin:/bin /tmp/cratory-altrove/python/bin/python3 -c "
import sys, essentia.standard, fastapi
print('prefix:', sys.prefix)
print('essentia e fastapi importano dal percorso nuovo')
"
```

Atteso: `sys.prefix` segue l'albero spostato e gli import passano. È il criterio che un `.venv` fallisce, ed è il motivo per cui si spedisce un runtime rilocabile invece di copiare il venv di sviluppo.

- [ ] **Step 4: Provare l'analisi vera**

```bash
cd backend && env -i PATH=/usr/bin:/bin HOME="$HOME" /tmp/cratory-altrove/python/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from app.integrations import essentia_engine as e
print('is_available:', e.is_available())
"
```

Atteso: `True`. Se è `False`, essentia non è importabile dal runtime e il bundle sarebbe inutile per la pagina Analisi: fermarsi e segnalare.

- [ ] **Step 5: Pulire e committare**

```bash
rm -rf /tmp/cratory-runtime-prova /tmp/cratory-altrove
git add src-tauri/scripts/costruisci_runtime.py
git commit -m "feat(tauri): script del runtime Python rilocabile

Verificato eseguendo, non ispezionando: un albero che estrae e installa
correttamente puo' comunque produrre un interprete che non importa essentia."
```

---

### Task 3: I tre binari esterni

**Files:**
- Create: `src-tauri/scripts/costruisci_binari.py`

**Interfaces:**
- Consumes: `backend/app/services/binary_manifest.entry_for(key)`.
- Produces: `costruisci_binari.py <destinazione>` che lascia in `<destinazione>/bin/` il layout che `system_probe.resolve_binary` conosce: `bin/fpcalc` (single), `bin/ffmpeg/ffmpeg` e `bin/slskd/slskd` (bundle).

**Il layout non è una scelta.** `resolve_binary` prova prima `<bin_dir>/<name>` e poi `<bin_dir>/<key>/<name>`. Sbagliarlo produce un bundle in cui il wizard dichiara i componenti mancanti mentre sono lì.

**fpcalc e slskd: leggere il manifest, non ricopiarlo.** `entry_for("fpcalc")` e `entry_for("slskd")` danno versione, URL, SHA256, tipo di archivio e nome dell'eseguibile per `darwin-arm64`. Se `backend/app/services/binary_installer.py` espone un punto d'ingresso pulito per «scarica, verifica, estrai in questa cartella», **riusarlo** invece di riscrivere quella logica; se non c'è, scrivere nello script la sequenza minima (scarica → verifica l'hash → estrai → esegui col `version_flag` per confermare che parte) senza mai incollare URL o hash.

**ffmpeg: rilocazione da Homebrew.** `entry_for("ffmpeg")` restituisce `None` su questa piattaforma di proposito. La procedura è stata provata e funziona; questa è la sua forma:

```python
def deps(binario: Path) -> list[str]:
    """Dipendenze non di sistema, dalla tabella di otool."""
    out = subprocess.run(["otool", "-L", str(binario)], capture_output=True, text=True).stdout
    righe = [r.split()[0] for r in out.splitlines()[1:] if r.strip()]
    return [r for r in righe if not r.startswith(("/usr/lib", "/System"))]
```

Poi: chiusura **transitiva** (una dylib copiata ha a sua volta dipendenze — con le sole dirette il binario non parte), copia in `bin/ffmpeg/`, riscrittura di ogni riferimento con
`install_name_tool -id @loader_path/<nome>` e `install_name_tool -change <vecchio> @loader_path/<nome>`, e **infine** `codesign --force --sign -` su ogni file, perché `install_name_tool` invalida la firma.

Lo script deve **fallire con un messaggio chiaro se Homebrew o ffmpeg non ci sono**: è un requisito della macchina di build, non dell'utente finale, e va detto a chi costruisce.

- [ ] **Step 1: Scrivere lo script**

Implementare quanto sopra in `src-tauri/scripts/costruisci_binari.py`, con la stessa disciplina del Task 2: idempotente, e alla fine **esegue ogni binario** col proprio `version_flag`, fallendo se uno non parte.

- [ ] **Step 2: Eseguirlo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805
python3 src-tauri/scripts/costruisci_binari.py /tmp/cratory-bin-prova
find /tmp/cratory-bin-prova -maxdepth 2 -type f -perm +111 | sort
```

Atteso: `bin/fpcalc`, `bin/ffmpeg/ffmpeg`, `bin/slskd/slskd`, più le dylib accanto a ffmpeg.

- [ ] **Step 3: La prova che conta — eseguirli da altrove, senza Homebrew**

```bash
mkdir -p /tmp/cratory-bin-altrove && cp -R /tmp/cratory-bin-prova/bin /tmp/cratory-bin-altrove/
env -i PATH=/usr/bin:/bin /tmp/cratory-bin-altrove/bin/ffmpeg/ffmpeg -version | head -1
env -i PATH=/usr/bin:/bin /tmp/cratory-bin-altrove/bin/fpcalc -version | head -1
env -i PATH=/usr/bin:/bin /tmp/cratory-bin-altrove/bin/slskd/slskd --version | head -1
echo "--- riferimenti residui a Homebrew (deve essere 0) ---"
otool -L /tmp/cratory-bin-altrove/bin/ffmpeg/ffmpeg | grep -c "/opt/homebrew"
```

Atteso: le tre versioni stampate, e **0** riferimenti a `/opt/homebrew`. Un numero diverso da zero significa che la chiusura transitiva ha saltato qualcosa: riportarlo, non aggirarlo.

- [ ] **Step 4: Verificare che il probe del backend li riconosca**

È il vero criterio: non basta che i binari esistano, deve trovarli il codice che li userà.

```bash
cd backend && CRATORY_BIN_DIR=/tmp/cratory-bin-altrove/bin \
  /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from app.services import system_probe as sp
for nome in ('ffmpeg','fpcalc'):
    print(f'  {nome}:', sp.resolve_binary(nome))
"
```

Atteso: entrambi risolvono dentro `/tmp/cratory-bin-altrove/bin`, **non** su `/opt/homebrew` né altrove nel `PATH`. Se risolvono altrove, il layout non combacia con quello che `resolve_binary` si aspetta.

- [ ] **Step 5: Pulire e committare**

```bash
rm -rf /tmp/cratory-bin-prova /tmp/cratory-bin-altrove
git add src-tauri/scripts/costruisci_binari.py
git commit -m "feat(tauri): i tre binari esterni nel bundle

ffmpeg rilocato da Homebrew perche' nessun upstream pubblica una build arm64
con checksum; fpcalc e slskd letti dal manifest, non ricopiati."
```

---

### Task 4: Il ciclo di vita del backend

**Files:**
- Modify: `src-tauri/src/main.rs` (o il modulo che lo scaffold ha creato)

**Interfaces:**
- Consumes: lo scaffold del Task 1.
- Produces: all'avvio dell'app il backend gira e risponde; alla chiusura muore.

**Perché questo task non contiene codice Rust, a differenza di tutti gli altri.**
Il resto del piano detta il codice esatto perché chi lo ha scritto lo ha
verificato. Qui no: l'API di Tauri v2 cambia fra minor, e dettare firme
ricordate a memoria produrrebbe codice che sembra autorevole e non compila — o
peggio, compila per caso facendo un'altra cosa. Il task specifica quindi i
**comportamenti** e i **criteri di verifica**, che sono stabili, e lascia le
chiamate a chi legge la documentazione della versione installata.

**Prima di scrivere una riga:** leggere lì come si ottiene il percorso delle
risorse del bundle e come ci si aggancia agli eventi di avvio e di chiusura.

Quattro comportamenti, in quest'ordine:

1. **Prima di tutto, controllare la porta 8000.** Se è occupata, mostrare un errore e uscire. Il messaggio deve distinguere «c'è già un Cratory aperto» da «un altro programma usa la 8000», perché sono azioni diverse per l'utente. Non cercare un'altra porta: `spotify_redirect_uri` è registrata su Spotify con la 8000.
2. **Avviare il backend** come processo figlio: `<risorse>/python/bin/python3 -m uvicorn app.main:app --port 8000 --host 127.0.0.1`, con cwd `<risorse>/backend`, e con l'ambiente che porta `CRATORY_DATA_DIR`, `CRATORY_BIN_DIR` e `CRATORY_VERSION` (il cablaggio esatto è il Task 5; qui basta che il meccanismo ci sia).
3. **Aspettare che risponda** interrogando `http://127.0.0.1:8000/api/setup/state` a intervalli, con un limite di tempo. Mostrare la finestra **solo dopo**: aprirla prima dà una pagina bianca o un muro di errori mentre il backend sale. Se il limite scade, dire che il backend non è partito e mostrare le ultime righe del suo output invece di una finestra vuota.
4. **Alla chiusura, terminare il figlio.** Un backend orfano attaccato alla 8000 rende il secondo avvio un fallimento inspiegabile — ed è esattamente il caso che il punto 1 poi segnalerebbe, confondendo la causa con l'effetto.

- [ ] **Step 1: Implementare**

In `src-tauri/src/`, con commenti in italiano che dicano **perché**, non cosa. In particolare il commento sulla porta fissa deve nominare `spotify_redirect_uri`, altrimenti fra sei mesi qualcuno "migliorerà" il codice cercando una porta libera.

- [ ] **Step 2: Provare l'avvio**

```bash
cd frontend && npm run tauri:dev
```

Atteso: la finestra compare **dopo** che il backend risponde, e l'interfaccia carica i dati veri. Riportare quanto tempo passa fra il lancio e la comparsa della finestra.

- [ ] **Step 3: Provare i tre casi che vanno storti**

Uno alla volta, riportando cosa si è visto davvero:

```bash
# (a) porta occupata da altro
python3 -m http.server 8000 &
cd frontend && npm run tauri:dev
# atteso: errore leggibile, nessuna finestra vuota. Poi: kill %1
```

```bash
# (b) nessun processo orfano dopo la chiusura
cd frontend && npm run tauri:dev   # chiudere la finestra dalla UI
pgrep -fl "uvicorn app.main" || echo "  nessun backend orfano: corretto"
```

```bash
# (c) riavvio immediato
cd frontend && npm run tauri:dev   # deve ripartire, cioe' la porta e' stata liberata
```

- [ ] **Step 4: Commit**

```bash
git add -A src-tauri
git commit -m "feat(tauri): avvio, attesa e spegnimento del backend

La finestra compare dopo che il backend risponde: aprirla prima mostrerebbe
una pagina bianca. La porta 8000 e' fissa perche' la redirect URI di Spotify
e' registrata su quel numero."
```

---

### Task 5: L'assemblaggio e le variabili

**Files:**
- Create: `src-tauri/scripts/assembla.py`
- Modify: `src-tauri/tauri.conf.json` (le risorse da includere)

**Interfaces:**
- Consumes: `costruisci_runtime.py` (Task 2), `costruisci_binari.py` (Task 3), il guscio (Task 4).
- Produces: `Cratory.app` completo.

- [ ] **Step 1: Scrivere lo script di assemblaggio**

`src-tauri/scripts/assembla.py` fa, in ordine:

1. `CRATORY_STATIC_EXPORT=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build` in `frontend/`.
2. `costruisci_runtime.py` verso la cartella di staging.
3. `costruisci_binari.py` verso la stessa.
4. Copia di `backend/app` e `backend/requirements.txt` nello staging, **escludendo** `tests/`, `__pycache__`, `data/`, `logs/`.
5. `npm run tauri:build`.

- [ ] **Step 2: Dichiarare le risorse in `tauri.conf.json`**

Aggiungere allo `bundle` le risorse dello staging, così che finiscano in `Contents/Resources/`. La forma esatta della chiave va letta dalla documentazione della versione installata.

- [ ] **Step 3: Cablare le tre variabili**

Nel guscio, al momento di lanciare il backend:

- `CRATORY_DATA_DIR` → la cartella dati dell'app per l'utente, cioè `~/Library/Application Support/Cratory`. Prenderla dall'API di Tauri per le directory dell'app, non comporla a mano.
- `CRATORY_BIN_DIR` → `<risorse>/bin`.
- `CRATORY_VERSION` → il numero dal file `VERSION`, letto a build time e incorporato; nel bundle non c'è nessuna radice di repository da cui leggerlo.

- [ ] **Step 4: Costruire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805
python3 src-tauri/scripts/assembla.py
```

Atteso: un `Cratory.app` sotto `src-tauri/target/`. Riportarne la dimensione.

- [ ] **Step 5: Verificare il contenuto prima di aprirlo**

```bash
APP=$(find src-tauri/target -name "Cratory.app" -maxdepth 4 | head -1)
ls "$APP/Contents/Resources/"
find "$APP/Contents/Resources/bin" -maxdepth 2 -type f -perm +111 | sort
test -f "$APP/Contents/Resources/python/bin/python3" && echo "  runtime presente"
test -d "$APP/Contents/Resources/frontend" && echo "  frontend presente"
```

Atteso: `frontend/`, `python/`, `backend/`, `bin/` tutti presenti, coi tre binari eseguibili.

- [ ] **Step 6: Verificare la firma ad-hoc**

Su Apple Silicon un binario senza firma non esegue proprio, e `install_name_tool`
del Task 3 invalida quella delle dylib di ffmpeg. Tauri firma ad-hoc il bundle,
ma va confermato che copra anche le risorse:

```bash
APP=$(find src-tauri/target -name "Cratory.app" -maxdepth 4 | head -1)
codesign --verify --deep --verbose=2 "$APP" 2>&1 | tail -5
codesign -dv "$APP/Contents/Resources/bin/ffmpeg/ffmpeg" 2>&1 | grep -i "signature"
```

Atteso: la verifica passa e ffmpeg risulta firmato ad-hoc. Se `--deep` segnala
una risorsa non firmata, firmarla nello script di assemblaggio **dopo** la
rilocazione e **prima** di `tauri build`, e riportare quale file era.

- [ ] **Step 7: Commit**

```bash
git add -A src-tauri
git commit -m "feat(tauri): assemblaggio del bundle e cablaggio dei tre seam

CRATORY_DATA_DIR, CRATORY_BIN_DIR e CRATORY_VERSION arrivano dal guscio: nel
backend non cambia una riga, che era il punto di averli scritti cosi'."
```

---

### Task 6: La verifica dal doppio clic

**Files:** nessuno modificato, salvo le correzioni che questa verifica rende necessarie.

Il criterio del ③ non è «compila», è **«funziona da un doppio clic»**. Ogni punto va eseguito e riportato con quello che si è visto davvero.

- [ ] **Step 1: Aprire l'app copiata altrove**

```bash
APP=$(find src-tauri/target -name "Cratory.app" -maxdepth 4 | head -1)
cp -R "$APP" /tmp/Cratory-prova.app
open /tmp/Cratory-prova.app
```

Copiarla altrove **prima** di aprirla non è pedanteria: è la prova che niente dipende dal percorso di build. Se funziona solo in `target/`, il bundle è rotto per chiunque altro.

- [ ] **Step 2: I dati stanno fuori dal bundle**

```bash
ls -la ~/Library/Application\ Support/Cratory/ 2>/dev/null
find /tmp/Cratory-prova.app -name "*.db" -o -name "logs" -type d
```

Atteso: database e log sotto `Application Support`; **niente** dentro il `.app`. È l'invariante del ①, qui verificata sul prodotto finito.

- [ ] **Step 3: Le due prove che i binari del bundle funzionano davvero**

- Aprire la pagina **Analisi** e analizzare una traccia: un BPM plausibile prova che essentia gira dal runtime del bundle.
- Riprodurre una traccia posseduta: prova che ffmpeg rilocato funziona.

Se la libreria è vuota, dirlo e usare un file di prova invece di dichiarare il punto verificato.

- [ ] **Step 4: La domanda che il ② ha lasciato aperta**

Navigare a una rotta di dettaglio (per esempio una traccia dalla libreria) e verificare se l'URL senza estensione risolve. L'export produce `out/tracks.html`: `npx serve` mappa `/tracks` su quel file, il protocollo asset di Tauri **potrebbe non farlo**.

Se non risolve, aggiungere `trailingSlash: true` sotto `CRATORY_STATIC_EXPORT` in `frontend/next.config.ts` — che fa produrre `out/tracks/index.html` — ricostruire e riverificare. Riportare quale dei due casi si è presentato: è un'informazione che la spec del ② chiedeva esplicitamente di raccogliere guardando, non ragionando.

- [ ] **Step 5: Chiusura e riapertura**

Chiudere la finestra, poi:

```bash
pgrep -fl "uvicorn app.main" || echo "  nessun backend orfano"
open /tmp/Cratory-prova.app   # deve riaprirsi
```

- [ ] **Step 6: Pulire e committare le eventuali correzioni**

```bash
rm -rf /tmp/Cratory-prova.app
```

Se i passi precedenti hanno richiesto modifiche, committarle con un messaggio che dica **quale verifica** le ha rese necessarie.

---

### Task 7: La documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `PROGRESS.md`, `README.md`

- [ ] **Step 1: `README.md`**

Il README descrive l'avvio da `start-dev.sh`. Aggiungere una sezione sul bundle desktop: come si costruisce (`python3 src-tauri/scripts/assembla.py`), che serve Homebrew **sulla macchina di build** per ffmpeg, e che l'app non è ancora firmata da Apple — la parte sulla quarantena e sul `.dmg` è il ④ e **non va anticipata qui**.

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Una sezione sul guscio: cosa contiene il bundle, perché un CPython rilocabile invece di un binario congelato, perché la porta è fissa, e come i tre seam si incastrano. È il posto dove il «perché» sopravvive.

- [ ] **Step 3: `docs/ROADMAP.md` e `PROGRESS.md`**

La voce del ③, con la stessa cautela dei precedenti: **il `.dmg`, la firma e l'updater non esistono ancora**. Esiste un `.app` che si apre.

- [ ] **Step 4: Rileggere il diff cercando affermazioni false**

```bash
git diff docs/ PROGRESS.md README.md
```

Nessuna riga deve suggerire che l'app sia distribuibile: non lo è finché il ④ non esiste.

- [ ] **Step 5: Commit**

```bash
git add docs/ PROGRESS.md README.md
git commit -m "docs(tauri): il guscio, il bundle e i tre seam"
```

---

## Verifica finale

- [ ] `python3 src-tauri/scripts/assembla.py` produce un `Cratory.app` da zero.
- [ ] Il `.app` copiato in `/tmp` si apre e funziona.
- [ ] Analisi produce un BPM; una traccia posseduta si riproduce.
- [ ] I dati stanno in `~/Library/Application Support/Cratory/`, niente dentro il bundle.
- [ ] Chiusa la finestra, nessun processo Python resta vivo.
- [ ] `cd backend && python -m pytest tests -q` — nessun fallimento nuovo (il backend non doveva cambiare).
- [ ] `cd frontend && npm run test:unit && npm run lint` — verdi.
- [ ] `git status --porcelain` vuoto; `src-tauri/target/` e `frontend/out/` non tracciati.
