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
import subprocess
import sys
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
    return tar, sig, dmg


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
    args = parser.parse_args()

    versione = _versione()
    if not args.dry_run:
        _controlli(versione)
    tar, sig, dmg = _artefatti(versione)
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
