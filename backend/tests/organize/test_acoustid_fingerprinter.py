"""Seam Tauri: `_default_fingerprinter` (organize/integrations/acoustid.py)
deve risolvere fpcalc con lo stesso seam di `fpcalc_available()`.

pyacoustid non accetta un percorso come argomento: la sua funzione
`fingerprint_file` legge internamente `os.environ.get("FPCALC", "fpcalc")`
per trovare il binario. Senza questo fix, un'app lanciata dal Finder (PATH
minimo di launchd) direbbe "fpcalc disponibile" (il probe usa CRATORY_BIN_DIR)
ma il fingerprint fallirebbe comunque, perche' pyacoustid cercherebbe "fpcalc"
sul solo PATH.
"""

import os
import sys
import types

import pytest

from app.organize.integrations import acoustid
from app.services import system_probe as sp


def test_default_fingerprinter_imposta_env_fpcalc_dal_seam(tmp_path, monkeypatch):
    fake = tmp_path / "fpcalc"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.delenv("FPCALC", raising=False)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    # pyacoustid e' importato lazy dentro la funzione (`import acoustid as
    # pyacoustid`): un finto modulo in sys.modules intercetta la chiamata
    # senza bisogno di fpcalc/chromaprint veri installati.
    modulo_finto = types.SimpleNamespace(fingerprint_file=lambda path: (10, b"impronta"))
    monkeypatch.setitem(sys.modules, "acoustid", modulo_finto)

    try:
        durata, impronta = acoustid._default_fingerprinter("song.mp3")
        assert (durata, impronta) == (10, b"impronta")
        assert os.environ["FPCALC"] == str(fake), \
            "pyacoustid legge os.environ['FPCALC']: senza impostarla non trova il binario risolto"
    finally:
        os.environ.pop("FPCALC", None)


def test_default_fingerprinter_solleva_se_fpcalc_non_risolvibile(tmp_path, monkeypatch):
    monkeypatch.delenv("FPCALC", raising=False)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))  # vuota: nessun fpcalc dentro
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    def _esplodi(path):
        raise AssertionError("non doveva provare a fingerprintare senza un binario risolto")

    modulo_finto = types.SimpleNamespace(fingerprint_file=_esplodi)
    monkeypatch.setitem(sys.modules, "acoustid", modulo_finto)

    with pytest.raises(FileNotFoundError):
        acoustid._default_fingerprinter("song.mp3")
