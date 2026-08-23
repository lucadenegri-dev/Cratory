"""Pubblica una versione: manifesto dell'updater e release su GitHub.

Separato da `assembla.py` di proposito. Costruire e' ripetibile e innocuo;
pubblicare no: crea un artefatto pubblico che qualcun altro scarichera' e che
le app installate useranno per aggiornarsi da sole. Sono due gesti.

Uso:
    python3 src-tauri/scripts/pubblica.py --note-file NOTE.md
    python3 src-tauri/scripts/pubblica.py --note-file NOTE.md --dry-run
    python3 src-tauri/scripts/pubblica.py --note-file NOTE.md --dry-run \\
        --base-url http://127.0.0.1:8787 --manifest-out /tmp/prova/latest.json

Prima di pubblicare pretende che: l'albero di lavoro sia pulito, `VERSION` e
`frontend/package.json` dicano lo stesso numero, HEAD porti il tag `vX.Y.Z` di
quel numero, i tre artefatti esistano, e `gh` sia installato.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
BUNDLE = RADICE / "src-tauri" / "target" / "release" / "bundle"
ASSET = "Cratory.app.tar.gz"
REPO = "lucadenegri-dev/Cratory"
PIATTAFORMA = "darwin-aarch64"  # l'unico target che questo progetto costruisce


def costruisci_manifest(
    versione: str, note: str, firma: str, pub_date: str, base_url: str | None = None
) -> dict:
    """Il JSON che l'updater legge.

    `base_url` esiste per la verifica locale (un server statico invece di
    GitHub): la struttura del manifesto e' la stessa, cambia solo da dove si
    scarica, e cosi' quella che si prova e' la funzione vera.
    """
    if not re.fullmatch(r"\d+\.\d+\.\d+", versione):
        raise ValueError(f"versione non semver, e senza `v` iniziale: {versione!r}")
    if not firma.strip():
        raise ValueError(
            'firma vuota: un manifesto con `signature: ""` si pubblica senza '
            "lamentele e fallisce solo sul Mac di chi si aggiorna"
        )
    url = (
        f"{base_url.rstrip('/')}/{ASSET}"
        if base_url
        else f"https://github.com/{REPO}/releases/download/v{versione}/{ASSET}"
    )
    return {
        "version": versione,
        "notes": note,
        "pub_date": pub_date,
        "platforms": {PIATTAFORMA: {"signature": firma.strip(), "url": url}},
    }


# L'endpoint che deve essere compilato dentro l'app pubblicata. La
# configurazione dell'updater finisce nel binario a build time: se questa
# stringa non c'e', quel binario e' stato costruito con un override
# (`CRATORY_TAURI_EXTRA_CONFIG`, che punta l'updater a un server locale) e
# pubblicarlo darebbe a tutti un'app che cerca aggiornamenti su 127.0.0.1.
ENDPOINT_PRODUZIONE = b"releases/latest/download/latest.json"


def costruita_per_la_produzione(binario: bytes) -> bool:
    """La variabile d'ambiente della prova resta esportata nella shell molto
    piu' a lungo di quanto la si ricordi: questo controllo esiste perche' quel
    dimenticarsene non sia pubblicabile."""
    return ENDPOINT_PRODUZIONE in binario


def _git(*argomenti: str) -> str:
    return subprocess.run(
        ["git", *argomenti], cwd=RADICE, capture_output=True, text=True, check=True
    ).stdout.strip()


def _versione() -> str:
    dal_file = (RADICE / "VERSION").read_text().strip()
    da_npm = json.loads((RADICE / "frontend" / "package.json").read_text())["version"]
    if dal_file != da_npm:
        raise SystemExit(f"VERSION dice {dal_file}, package.json dice {da_npm}")
    return dal_file


def _controlli(versione: str) -> None:
    if _git("status", "--porcelain"):
        raise SystemExit("albero di lavoro sporco: si pubblica solo cio' che e' committato")
    tag = f"v{versione}"
    if tag not in _git("tag", "--points-at", "HEAD").splitlines():
        raise SystemExit(f"HEAD non porta il tag {tag}")
    if subprocess.run(["which", "gh"], capture_output=True).returncode != 0:
        raise SystemExit("gh non e' installato: serve per creare la release")


def _artefatti(versione: str) -> tuple[Path, Path, Path]:
    tar = BUNDLE / "macos" / ASSET
    sig = BUNDLE / "macos" / f"{ASSET}.sig"
    dmg = BUNDLE / "dmg" / f"Cratory_{versione}_aarch64.dmg"
    for p in (tar, sig, dmg):
        if not p.is_file():
            raise SystemExit(f"manca {p} -- ricostruire con assembla.py")

    binario = BUNDLE / "macos" / "Cratory.app" / "Contents" / "MacOS" / "cratory"
    if not binario.is_file():
        raise SystemExit(f"manca {binario} -- serve il target `app`, non solo il dmg")
    if not costruita_per_la_produzione(binario.read_bytes()):
        raise SystemExit(
            "questa e' una build di prova: l'endpoint dell'updater compilato dentro\n"
            "l'app non e' quello pubblico. Succede quando CRATORY_TAURI_EXTRA_CONFIG\n"
            "e' rimasta esportata nella shell. Rimuovila e ricostruisci:\n"
            "  unset CRATORY_TAURI_EXTRA_CONFIG"
        )
    return tar, sig, dmg


def _avvia_e_interroga(app: Path, attesa_s: int = 90) -> str | None:
    """Lancia il bundle davvero e chiede al backend che versione e'.

    Ritorna `None` se tutto va bene, altrimenti il motivo. Termina sempre cio'
    che ha avviato, figlio compreso: il guscio uccide il backend quando esce,
    ma se e' morto prima di lanciarlo non c'e' niente da uccidere.
    """
    binario = app / "Contents" / "MacOS" / "cratory"
    if _porta_occupata():
        return (
            "la porta 8000 e' gia' occupata: chiudi Cratory (o il suo backend "
            "rimasto in esecuzione) prima di pubblicare, altrimenti questa "
            "prova risponderebbe per l'istanza sbagliata"
        )

    processo = subprocess.Popen(
        [str(binario)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        scadenza = time.monotonic() + attesa_s
        while time.monotonic() < scadenza:
            if processo.poll() is not None:
                return f"il guscio e' uscito da solo (codice {processo.returncode})"
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8000/api/version", timeout=2
                ) as risposta:
                    return None if json.load(risposta).get("version") else "nessuna versione"
            except Exception:
                time.sleep(2)
        return (
            f"il backend non ha risposto entro {attesa_s}s. Il guscio puo' essere "
            "vivo e la finestra invisibile: e' cosi' che si presenta un thread di "
            "avvio morto (vedi il test di regressione in src-tauri/src/backend.rs)"
        )
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=15)
        except subprocess.TimeoutExpired:
            processo.kill()


def _porta_occupata() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", 8000)) == 0


def _adesso() -> str:
    """RFC 3339, come lo vuole il manifesto."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--note-file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--manifest-out", type=Path, default=None)
    parser.add_argument(
        "--salta-avvio",
        dest="salta_avvio",
        action="store_true",
        help="non provare ad aprire il bundle (solo se non puoi eseguirlo qui)",
    )
    args = parser.parse_args()

    versione = _versione()
    if not args.dry_run:
        _controlli(versione)
    tar, sig, dmg = _artefatti(versione)

    if not args.dry_run and not args.salta_avvio:
        # Un bundle che non si apre non si pubblica. Il 2026-08-24 e' stata
        # pubblicata una 1.0.3 che partiva e restava invisibile per sempre: i
        # test erano tutti verdi, perche' nessuno di loro apriva l'app.
        print("--- prova di avvio del bundle ---")
        guasto = _avvia_e_interroga(BUNDLE / "macos" / "Cratory.app")
        if guasto:
            raise SystemExit(f"il bundle non si avvia: {guasto}")
        print("il bundle si avvia e il backend risponde.")
    note = args.note_file.read_text().strip()

    manifest = costruisci_manifest(
        versione=versione,
        note=note,
        firma=sig.read_text(),
        pub_date=_adesso(),
        base_url=args.base_url,
    )
    destinazione = args.manifest_out or (BUNDLE / "macos" / "latest.json")
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifesto scritto in {destinazione}")

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return

    tag = f"v{versione}"
    esiste = (
        subprocess.run(["gh", "release", "view", tag], cwd=RADICE, capture_output=True).returncode
        == 0
    )
    allegati = [str(dmg), str(tar), str(sig), str(destinazione)]
    if esiste:
        subprocess.run(
            ["gh", "release", "upload", tag, "--clobber", *allegati], cwd=RADICE, check=True
        )
    else:
        subprocess.run(
            ["gh", "release", "create", tag, "--title", tag,
             "--notes-file", str(args.note_file), *allegati],
            cwd=RADICE, check=True,
        )
    print(f"release {tag} pubblicata")


if __name__ == "__main__":
    main()
