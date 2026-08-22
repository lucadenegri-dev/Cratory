"""Costruisce la cartella dei tre binari esterni che il bundle Tauri porta con se'.

Uso:
    python3 src-tauri/scripts/costruisci_binari.py <destinazione>

Lascia in `<destinazione>/bin/` il layout che `backend/app/services/system_probe.
resolve_binary` conosce: prova prima `<bin_dir>/<nome>` (layout "single") e solo
dopo `<bin_dir>/<chiave>/<nome>` (layout "bundle"). Su questa piattaforma
(darwin-arm64) il risultato e':

    bin/fpcalc            (single)
    bin/slskd/slskd       (bundle: accanto ci sta il runtime .NET che porta con se')
    bin/ffmpeg/ffmpeg     (bundle: accanto ci stanno le sue dylib rilocate)

fpcalc e slskd si leggono da `backend/app/services/binary_manifest.entry_for`
(versione, URL, SHA256, tipo di archivio, nome dell'eseguibile, version_flag):
questo script non incolla mai quei valori, li rilegge a ogni run cosi' un bump
di versione nel manifesto si propaga qui senza toccare questo file.

Non si importa `backend/app/services/binary_installer.py`, nonostante offra
gia' una sequenza scarica-verifica-estrai: per arrivare alla cartella di
destinazione passa da `system_probe.managed_bin_dir()`, che importa
`app.core.runtime_settings`, e quello importa `sqlalchemy.orm.Session` e
`app.services.app_state` — l'intera pila del backend (SQLAlchemy,
pydantic-settings, httpx) solo per scaricare un file. Questo script, come
`costruisci_runtime.py`, deve girare con un `python3` nudo, prima che
qualunque venv esista: la sequenza scarica-verifica-estrai-prova e' percio'
riscritta qui con la sola stdlib. L'unico import dal backend e'
`app.services.binary_manifest`, dati puri (dataclass/platform/sys, nessuna
dipendenza pesante) senza il quale si dovrebbero ricopiare qui URL e hash.

ffmpeg non ha una voce nel manifesto su macOS arm64 (`entry_for("ffmpeg")`
ritorna None di proposito: nessun upstream pubblica una build arm64 nativa
con checksum). Si rilocalizza invece la build di Homebrew della MACCHINA DI
BUILD: chiusura transitiva delle dipendenze non di sistema (via `otool -L`),
copia accanto all'eseguibile, riscrittura di ogni riferimento con
`install_name_tool` e ri-firma ad-hoc alla fine (obbligatoria:
`install_name_tool` invalida la firma di ogni file che tocca, e su Apple
Silicon un binario non firmato non parte). Se Homebrew o ffmpeg non ci sono
sulla macchina di build, lo script si ferma con un messaggio esplicito: e' un
requisito di chi costruisce il bundle, non dell'utente finale che lo riceve
gia' completo.

Idempotente: se `<destinazione>/bin` esiste gia' viene ricostruita da zero,
non aggiornata in place.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_RADICE_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_RADICE_REPO / "backend"))
from app.services.binary_manifest import Download, entry_for, platform_tag  # noqa: E402

_TAR_SUPPORTA_FILTRO = "filter" in inspect.signature(tarfile.TarFile.extractall).parameters

# ffmpeg non ha una voce nel manifesto su questa piattaforma (vedi sopra): il
# suo flag di versione non viene quindi letto da nessun Download, e' il flag
# CLI documentato e stabile di ffmpeg stesso (lo stesso usato nello Step 3 del
# brief), non un valore che possa divergere per un bump di versione.
_FFMPEG_VERSION_FLAG = "-version"


def _esegui(argv: list[str]) -> str:
    """Esegue un comando esterno (otool/install_name_tool/codesign) e ritorna
    il suo stdout; solleva RuntimeError con comando e stderr se fallisce,
    cosi' ogni fallimento ha lo stesso stile di errore leggibile del resto
    dello script invece di un CalledProcessError grezzo."""
    esito = subprocess.run(argv, capture_output=True, text=True)
    if esito.returncode != 0:
        raise RuntimeError(
            f"comando fallito: {' '.join(argv)} (codice {esito.returncode})\n{esito.stderr.strip()}"
        )
    return esito.stdout


def _richiedi_comando(nome: str) -> None:
    if shutil.which(nome) is None:
        raise RuntimeError(
            f"comando '{nome}' non trovato sul PATH: servono gli Xcode Command "
            "Line Tools sulla macchina di build ('xcode-select --install')."
        )


# --------------------------------------------------------------------------
# fpcalc e slskd: scarica-verifica-estrai-prova dal manifesto.
# --------------------------------------------------------------------------


def _scarica_e_verifica(d: Download, cartella_tmp: Path) -> Path:
    """Scarica `d.url` dentro `cartella_tmp` e verifica lo SHA256 contro il
    pin nel manifesto.

    Stessa disciplina di `costruisci_runtime.py`: l'hash e' quello fissato
    nel manifesto, non un digest riletto al volo dalla stessa fonte che una
    release compromessa a monte controllerebbe."""
    archivio = cartella_tmp / f"archivio.{d.archive}"
    richiesta = urllib.request.Request(d.url, headers={"User-Agent": "cratory-costruisci-binari/1.0"})
    hasher = hashlib.sha256()
    with urllib.request.urlopen(richiesta) as risposta, open(archivio, "wb") as f:
        while True:
            chunk = risposta.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != d.sha256:
        raise RuntimeError(
            f"SHA256 non corrisponde per {d.url}\n"
            f"  atteso:   {d.sha256}\n"
            f"  ottenuto: {digest}\n"
            "L'archivio scaricato non e' quello pinnato nel manifesto "
            "(rilascio cambiato a monte o download corrotto): mi fermo, non lo estraggo."
        )
    return archivio


def _trova_membro(nomi: list[str], member: str) -> str:
    """Cerca il membro per basename dentro la lista di nomi dell'archivio: il
    percorso interno delle release spesso porta l'etichetta della build e
    cambia a ogni release."""
    for nome in nomi:
        if Path(nome).name == member:
            return nome
    raise RuntimeError(f"'{member}' non trovato nell'archivio")


def _estrai(archivio: Path, d: Download, cartella_lavoro: Path) -> Path:
    """Estrae l'archivio in `cartella_lavoro` e ritorna il percorso
    dell'eseguibile appena estratto.

    `single`: si estrae solo `d.member`. `bundle`: si estrae tutto l'archivio,
    perche' l'eseguibile non e' autosufficiente (slskd porta con se' il
    runtime .NET)."""
    cartella_lavoro.mkdir(parents=True, exist_ok=True)
    if d.archive == "zip":
        with zipfile.ZipFile(archivio) as z:
            interno = _trova_membro(z.namelist(), d.member)
            if d.layout == "bundle":
                z.extractall(cartella_lavoro)
            else:
                z.extract(interno, cartella_lavoro)
    else:
        modo = "r:xz" if d.archive == "tar.xz" else "r:gz"
        kwargs = {"filter": "data"} if _TAR_SUPPORTA_FILTRO else {}
        with tarfile.open(archivio, modo) as t:
            interno = _trova_membro(t.getnames(), d.member)
            if d.layout == "bundle":
                t.extractall(cartella_lavoro, **kwargs)
            else:
                t.extract(interno, cartella_lavoro, **kwargs)
    return cartella_lavoro / interno


def _rendi_eseguibile(percorso: Path) -> None:
    percorso.chmod(percorso.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _installa_singolo(archivio: Path, d: Download, bin_dir: Path) -> Path:
    """Layout 'single': l'eseguibile finisce direttamente in
    `bin_dir/<member>` (es. `bin/fpcalc`) — il primo posto in cui
    `resolve_binary` lo cerca."""
    with tempfile.TemporaryDirectory(prefix="cratory-bin-estrai-") as tmp:
        estratto = _estrai(archivio, d, Path(tmp))
        finale = bin_dir / d.member
        shutil.copy2(estratto, finale)
    _rendi_eseguibile(finale)
    return finale


def _installa_bundle(archivio: Path, d: Download, chiave: str, bin_dir: Path) -> Path:
    """Layout 'bundle': l'intera cartella che contiene l'eseguibile (i file
    accanto compresi, es. il runtime .NET di slskd) finisce in
    `bin_dir/<chiave>/` — il secondo posto in cui `resolve_binary` cerca,
    `<bin_dir>/<chiave>/<nome>`."""
    with tempfile.TemporaryDirectory(prefix="cratory-bin-estrai-") as tmp:
        estratto = _estrai(archivio, d, Path(tmp))
        cartella_finale = bin_dir / chiave
        shutil.copytree(estratto.parent, cartella_finale)
    finale = cartella_finale / d.member
    _rendi_eseguibile(finale)
    return finale


def _verifica_esecuzione(percorso: Path, version_flag: str, chiave: str) -> str:
    """Esegue il binario appena installato col proprio flag di versione: e'
    la verifica reale, download/hash/estrazione possono essere andati e il
    file puo' ancora non partire (firma, architettura, dipendenza mancante)."""
    try:
        esito = subprocess.run([str(percorso), version_flag], capture_output=True,
                               text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"{chiave}: '{percorso} {version_flag}' non parte: {exc}") from exc
    if esito.returncode != 0:
        dettaglio = (esito.stderr or esito.stdout or "").strip()[:200]
        raise RuntimeError(
            f"{chiave}: '{percorso} {version_flag}' e' uscito con codice "
            f"{esito.returncode}: {dettaglio}"
        )
    output = (esito.stdout or esito.stderr or "").strip()
    return output.splitlines()[0][:120] if output else "(nessun output)"


def _installa_da_manifesto(chiave: str, bin_dir: Path) -> Path:
    """Scarica, verifica, estrae, installa e prova un componente letto dal
    manifesto (`entry_for`): non incolla mai URL, hash o nome dell'eseguibile,
    li rilegge a ogni run."""
    d = entry_for(chiave)
    if d is None:
        raise RuntimeError(
            f"'{chiave}' non ha una voce nel manifesto per questa piattaforma "
            f"({platform_tag()}). Verificare backend/app/services/binary_manifest.py."
        )
    print(f"[{chiave}] scarico {d.url} ...")
    with tempfile.TemporaryDirectory(prefix=f"cratory-bin-dl-{chiave}-") as tmp:
        archivio = _scarica_e_verifica(d, Path(tmp))
        print(f"[{chiave}] SHA256 verificato ({d.sha256[:12]}...).")
        if d.layout == "single":
            finale = _installa_singolo(archivio, d, bin_dir)
        else:
            finale = _installa_bundle(archivio, d, chiave, bin_dir)
    versione = _verifica_esecuzione(finale, d.version_flag, chiave)
    print(f"[{chiave}] installato in {finale}, parte: {versione}")
    return finale


# --------------------------------------------------------------------------
# ffmpeg: rilocazione da Homebrew (nessuna build arm64 con checksum a monte).
# --------------------------------------------------------------------------


def _homebrew_ffmpeg() -> tuple[Path, Path]:
    """Percorso di ffmpeg installato da Homebrew sulla macchina di build, o
    solleva con un messaggio chiaro se Homebrew o ffmpeg non ci sono: e' un
    requisito della macchina che costruisce il bundle, non dell'utente finale
    che lo riceve gia' completo."""
    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError(
            "Homebrew non e' installato su QUESTA macchina di build (comando "
            "'brew' non trovato sul PATH). ffmpeg non ha una build arm64 con "
            "checksum pubblicato a monte: su macOS lo si rilocalizza da "
            "un'installazione Homebrew esistente. Installare Homebrew "
            "(https://brew.sh) e poi 'brew install ffmpeg' su questa stessa "
            "macchina prima di ricostruire i binari."
        )
    esito = subprocess.run([brew, "--prefix", "ffmpeg"], capture_output=True, text=True)
    if esito.returncode != 0:
        raise RuntimeError(
            "ffmpeg non risulta installato via Homebrew su QUESTA macchina di "
            f"build ('{brew} --prefix ffmpeg' e' uscito con codice "
            f"{esito.returncode}). Eseguire 'brew install ffmpeg' su questa "
            "stessa macchina prima di ricostruire i binari."
        )
    prefix = Path(esito.stdout.strip())
    binario = prefix / "bin" / "ffmpeg"
    sonda = prefix / "bin" / "ffprobe"
    # Entrambi, non solo ffmpeg: sono due eseguibili della stessa formula, e
    # senza ffprobe Shazam non ricava la durata del mix.
    for atteso in (binario, sonda):
        if not atteso.is_file():
            raise RuntimeError(
                f"'{atteso}' non esiste nonostante Homebrew dichiari ffmpeg "
                f"installato in '{prefix}' su questa macchina di build. "
                "Eseguire 'brew reinstall ffmpeg' su questa stessa macchina."
            )
    return binario, sonda


def _deps(binario: Path) -> list[str]:
    """Dipendenze non di sistema di `binario`, dalla tabella di `otool -L`
    (la prima riga e' l'id del file stesso, non una dipendenza: la si
    scarta)."""
    out = _esegui(["otool", "-L", str(binario)])
    righe = [r.split()[0] for r in out.splitlines()[1:] if r.strip()]
    return [r for r in righe if not r.startswith(("/usr/lib", "/System"))]


def _chiusura_transitiva(radice: Path) -> set[Path]:
    """Tutte le dylib raggiungibili da `radice` seguendo le dipendenze non di
    sistema, ricorsivamente: una dylib copiata ha a sua volta dipendenze, e
    con le sole dirette il binario copiato non parte.

    Ogni percorso si canonicalizza con `.resolve()` prima di entrare in
    `viste`/nel risultato: Homebrew referenzia la stessa libreria con
    percorsi diversi a seconda di chi la richiede — `/opt/homebrew/opt/<pkg>/
    lib/...` (il symlink stabile fra versioni, per le dipendenze da un'altra
    formula) oppure `/opt/homebrew/Cellar/<pkg>/<versione>/lib/...` (il
    percorso reale, per le librerie della stessa formula di chi dipende).
    Senza normalizzare, la stessa dylib fisica finirebbe visitata due volte e
    scambiata per due file distinti con lo stesso basename."""
    da_visitare = [radice]
    viste: set[Path] = set()
    dylib: set[Path] = set()
    while da_visitare:
        corrente = da_visitare.pop()
        canonico = corrente.resolve()
        if canonico in viste:
            continue
        viste.add(canonico)
        for dep in _deps(corrente):
            percorso = Path(dep).resolve()
            dylib.add(percorso)
            if percorso not in viste:
                da_visitare.append(percorso)
    return dylib


def _prerequisiti_ffmpeg() -> tuple[Path, Path]:
    """Controlla tutto cio' che serve alla rilocazione PRIMA di scaricare
    qualsiasi cosa (fpcalc/slskd inclusi): Homebrew, ffmpeg installato,
    otool/install_name_tool/codesign sul PATH. Meglio fermarsi qui, subito,
    che dopo aver gia' speso tempo e banda sugli altri due componenti.
    Ritorna i percorsi di ffmpeg e ffprobe da rilocalizzare."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "la rilocazione di ffmpeg da Homebrew e' implementata solo per "
            f"macOS (sys.platform={sys.platform!r})."
        )
    for comando in ("otool", "install_name_tool", "codesign"):
        _richiedi_comando(comando)
    return _homebrew_ffmpeg()


def _rilocalizza(nome: str, sorgente: Path, bin_dir: Path) -> Path:
    """Copia un binario di Homebrew (`sorgente`, gia' verificato da
    `_prerequisiti_ffmpeg`) e la chiusura transitiva delle sue dylib dentro
    `bin_dir/<nome>/`, riscrive ogni riferimento a essere relativo al binario
    stesso e ri-firma. Il risultato gira da qualunque percorso, senza
    Homebrew e senza le variabili d'ambiente che Homebrew normalmente
    fornisce (verificato su questa macchina con `env -i` da una cartella
    diversa — Step 3 del brief)."""
    print(f"[{nome}] rilocalizzo da {sorgente} ...")

    cartella_finale = bin_dir / nome
    cartella_finale.mkdir(parents=True)

    binario_finale = cartella_finale / nome
    shutil.copy2(sorgente, binario_finale)
    _rendi_eseguibile(binario_finale)

    dylib_originali = _chiusura_transitiva(sorgente)
    print(f"[{nome}] chiusura transitiva: {len(dylib_originali)} dylib.")

    percorso_finale_per_originale: dict[Path, Path] = {}
    for originale in dylib_originali:
        finale = cartella_finale / originale.name
        if finale.exists():
            raise RuntimeError(
                f"nome dylib duplicato nella chiusura transitiva: '{originale.name}' "
                f"(da {originale}) — due dylib con lo stesso basename non possono "
                "convivere in @loader_path, questo script non sa come rinominarle."
            )
        shutil.copy2(originale, finale)
        _rendi_eseguibile(finale)
        percorso_finale_per_originale[originale] = finale

    # Riscrittura dei riferimenti PRIMA della firma: install_name_tool
    # invalida la firma di ogni file che tocca, quindi la firma va fatta
    # dopo, una volta sola, a riscrittura completata su tutti i file.
    def _riscrivi_riferimenti(binario: Path, sorgente_originale: Path) -> None:
        for dep in _deps(sorgente_originale):
            # `dep` e' il percorso esatto (symlink o Cellar) come compare nel
            # binario: e' l'unico valore valido per "-change" (deve
            # combaciare col load command). Per la ricerca nella mappa serve
            # pero' il suo canonico, non la stringa grezza — vedi
            # `_chiusura_transitiva`.
            finale_dep = percorso_finale_per_originale.get(Path(dep).resolve())
            if finale_dep is None:
                continue  # dipendenza di sistema, non rilocata
            _esegui(["install_name_tool", "-change", dep,
                    f"@loader_path/{finale_dep.name}", str(binario)])

    _riscrivi_riferimenti(binario_finale, sorgente)
    for originale, finale in percorso_finale_per_originale.items():
        _esegui(["install_name_tool", "-id", f"@loader_path/{finale.name}", str(finale)])
        _riscrivi_riferimenti(finale, originale)

    # Ri-firma per ultima, su ogni file toccato: su Apple Silicon un binario
    # non firmato non parte affatto.
    for file in [binario_finale, *percorso_finale_per_originale.values()]:
        _esegui(["codesign", "--force", "--sign", "-", str(file)])

    return binario_finale


# --------------------------------------------------------------------------


def _dimensione(cartella: Path) -> str:
    """Dimensione su disco di `cartella`, stessa convenzione di `du -sh`
    (blocchi, non somma esatta dei byte): solo per il messaggio finale, non
    per nessuna decisione dello script."""
    try:
        esito = subprocess.run(["du", "-sh", str(cartella)], capture_output=True, text=True, check=True)
        return esito.stdout.split()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        totale = sum((Path(root) / nome).lstat().st_size
                    for root, _dirs, files in os.walk(cartella)
                    for nome in files)
        return f"{totale / (1024 * 1024):.1f}M (stima sui byte apparenti: 'du' non disponibile)"


def costruisci(destinazione: Path) -> None:
    print(f"Piattaforma: {platform_tag()}")

    # Prerequisiti di ffmpeg controllati per primi: se Homebrew o ffmpeg
    # mancano sulla macchina di build, meglio saperlo subito che dopo aver
    # gia' scaricato fpcalc e slskd per niente.
    ffmpeg_sorgente, ffprobe_sorgente = _prerequisiti_ffmpeg()

    destinazione = destinazione.resolve()
    bin_dir = destinazione / "bin"
    if bin_dir.exists():
        print(f"'{bin_dir}' esiste gia': la ricostruisco da zero (idempotente).")
        shutil.rmtree(bin_dir)
    bin_dir.mkdir(parents=True)

    print("--- fpcalc ---")
    _installa_da_manifesto("fpcalc", bin_dir)

    print("--- slskd ---")
    _installa_da_manifesto("slskd", bin_dir)

    # ffmpeg e ffprobe sono due eseguibili della stessa formula di Homebrew, e
    # `resolve_binary` cerca ognuno nella propria sottocartella: ffprobe non
    # puo' stare dentro bin/ffmpeg/. Ognuno si porta la propria chiusura di
    # dylib — sono quasi le stesse, ma condividerle vorrebbe dire symlink
    # dentro un bundle firmato, e la duplicazione costa meno del rischio.
    # Senza ffprobe, Shazam non ricava la durata del mix e produce una
    # tracklist di un segmento solo, senza dire perche'.
    for nome_bin, sorgente in (("ffmpeg", ffmpeg_sorgente), ("ffprobe", ffprobe_sorgente)):
        print(f"--- {nome_bin} ---")
        finale = _rilocalizza(nome_bin, sorgente, bin_dir)
        versione = _verifica_esecuzione(finale, _FFMPEG_VERSION_FLAG, nome_bin)
        print(f"[{nome_bin}] installato in {finale}, parte: {versione}")

    dimensione = _dimensione(bin_dir)
    print(f"Fatto: binari in {bin_dir} ({dimensione}).")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} <destinazione>", file=sys.stderr)
        raise SystemExit(2)
    try:
        costruisci(Path(sys.argv[1]))
    except Exception as errore:  # noqa: BLE001
        # I fallimenti previsti (RuntimeError: hash sbagliato, comando
        # esterno fallito, binario che non parte, Homebrew/ffmpeg assenti,
        # ...) hanno gia' un messaggio che dice cosa e' andato storto.
        # Qualunque altra eccezione imprevista merita lo stesso trattamento
        # leggibile invece di un traceback grezzo: chi lancia questo script
        # da terminale/CI legge stderr, non uno stack trace Python.
        print(f"ERRORE: {errore}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
