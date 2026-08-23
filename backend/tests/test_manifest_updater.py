"""Il manifesto che l'updater legge. Sei modi di sbagliarlo, tutti silenziosi:
un manifesto malformato non fa rumore, semplicemente nessuno si aggiorna più.
"""
import importlib.util
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "pubblica", RADICE / "src-tauri" / "scripts" / "pubblica.py"
)
pubblica = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pubblica)

FIRMA = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZQpSVQ==\n"
QUANDO = "2026-08-23T10:00:00Z"


def manifesto(**extra):
    argomenti = dict(versione="1.0.3", note="Note.", firma=FIRMA, pub_date=QUANDO)
    argomenti.update(extra)
    return pubblica.costruisci_manifest(**argomenti)


def test_la_firma_e_il_contenuto_del_sig_non_un_percorso():
    piattaforma = manifesto()["platforms"]["darwin-aarch64"]
    assert piattaforma["signature"] == FIRMA.strip()


def test_l_url_punta_all_asset_di_quel_tag_non_a_latest():
    url = manifesto()["platforms"]["darwin-aarch64"]["url"]
    assert url == (
        "https://github.com/lucadenegri-dev/Cratory/releases/download/"
        "v1.0.3/Cratory.app.tar.gz"
    )
    assert "/latest/" not in url


def test_la_versione_non_porta_la_v():
    assert manifesto()["version"] == "1.0.3"


def test_la_data_e_le_note_finiscono_nel_manifesto():
    m = manifesto()
    assert m["pub_date"] == QUANDO
    assert m["notes"] == "Note."


def test_una_firma_vuota_e_un_errore_non_un_manifesto_senza_firma():
    """Un manifesto con `signature: ""` viene pubblicato senza lamentele e
    fallisce solo sul Mac di chi si aggiorna."""
    with pytest.raises(ValueError):
        manifesto(firma="   \n")


def test_una_versione_non_semver_e_un_errore():
    with pytest.raises(ValueError):
        manifesto(versione="v1.0.3")
    with pytest.raises(ValueError):
        manifesto(versione="1.0")


def test_base_url_serve_la_verifica_locale():
    """La verifica sul campo serve gli artefatti da un server statico: stessa
    funzione, stessa struttura, altro host."""
    url = manifesto(base_url="http://127.0.0.1:8787")["platforms"]["darwin-aarch64"]["url"]
    assert url == "http://127.0.0.1:8787/Cratory.app.tar.gz"


def test_una_build_di_prova_non_e_pubblicabile():
    """L'endpoint dell'updater finisce dentro il binario a build time. Se è
    quello locale, l'app pubblicata cercherebbe aggiornamenti su 127.0.0.1 —
    e la sola traccia sarebbe che nessuno si aggiorna mai."""
    assert not pubblica.costruita_per_la_produzione(
        b"...http://127.0.0.1:8787/latest.json..."
    )


def test_una_build_normale_lo_e():
    assert pubblica.costruita_per_la_produzione(
        b"...https://github.com/lucadenegri-dev/Cratory/releases/latest/download/latest.json..."
    )
