"""La configurazione dell'updater è codice: se qualcuno la spegne, va detto.

Questi test non provano il funzionamento dell'updater — per quello serve un
bundle vero — ma che la configurazione spedita non possa degradare in silenzio
verso "non aggiorna nulla" o "accetta un manifesto da chiunque".
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent.parent
CONF = json.loads((RADICE / "src-tauri" / "tauri.conf.json").read_text())
ENDPOINT = "https://github.com/lucadenegri-dev/Cratory/releases/latest/download/latest.json"


def test_il_bundle_produce_gli_artefatti_dell_updater():
    """Senza questo flag `tauri build` fa solo il .dmg, e la release non ha
    niente che un'app già installata possa scaricare."""
    assert CONF["bundle"]["createUpdaterArtifacts"] is True


def test_il_target_app_e_fra_quelli_costruiti():
    """`createUpdaterArtifacts` da solo non basta, e questa è la lezione che è
    costata una build da venti minuti.

    L'artefatto che l'updater scarica su macOS è `Cratory.app.tar.gz`, e nasce
    dal target `app`. Con `targets: ["dmg"]` il bundler produce il .dmg e
    lascia `bundle/macos/` vuota: nessun tar.gz, nessun .sig, nessun errore —
    la build finisce con successo e la release sarebbe pubblicabile senza
    niente da aggiornare dentro. Il .dmg resta e resta necessario: è la prima
    installazione, quella che l'updater non può fare."""
    assert "app" in CONF["bundle"]["targets"]
    assert "dmg" in CONF["bundle"]["targets"]


def test_la_chiave_pubblica_c_e_ed_e_una_chiave():
    pubkey = CONF["plugins"]["updater"]["pubkey"]
    # Il .pub di minisign è una riga base64 di un centinaio di caratteri: un
    # placeholder o una stringa vuota non passano di qui.
    assert len(pubkey) > 40
    assert " " not in pubkey
    # `pubkey` vuole il CONTENUTO del .pub, non il percorso del file: un
    # percorso passerebbe il controllo sulla lunghezza e fallirebbe a runtime.
    assert not pubkey.startswith(("~", "/", "."))


def test_l_endpoint_e_quello_della_release_pubblica():
    assert CONF["plugins"]["updater"]["endpoints"] == [ENDPOINT]


def test_niente_http_in_chiaro_nella_configurazione_spedita():
    """L'override per la verifica locale passa da `tauri build --config`. Se
    quel flag finisse nel file committato, l'app spedita accetterebbe un
    manifesto servito da chiunque su http."""
    assert "dangerousInsecureTransportProtocol" not in CONF["plugins"]["updater"]


def test_assembla_si_ferma_subito_senza_chiave_di_firma():
    """Il controllo deve stare PRIMA di tutto il lavoro, non alla fine.

    Il `timeout` è metà dell'asserzione: se il controllo finisse dopo il
    preflight o dopo la build del frontend, questo test non fallirebbe con un
    messaggio — si pianterebbe. Trenta secondi sono un'eternità per un
    controllo su una variabile d'ambiente, e infinitamente meno dei ~20 minuti
    di una build vera.
    """
    ambiente = {k: v for k, v in os.environ.items() if k != "TAURI_SIGNING_PRIVATE_KEY"}
    esito = subprocess.run(
        [sys.executable, str(RADICE / "src-tauri" / "scripts" / "assembla.py")],
        capture_output=True, text=True, env=ambiente, timeout=30,
    )
    assert esito.returncode != 0
    assert "TAURI_SIGNING_PRIVATE_KEY" in esito.stdout + esito.stderr


def _assembla():
    """Caricato per percorso: `src-tauri/scripts/` non è un pacchetto
    importabile, e lo script aggiunge da sé la propria cartella a sys.path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "assembla", RADICE / "src-tauri" / "scripts" / "assembla.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_una_chiave_inutilizzabile_ferma_la_build_con_un_messaggio_utile():
    """Che la variabile esista non dice che la password sia giusta, e scoprirlo
    alla fine di `tauri build` costa l'intera build. Qui si prova che un
    fallimento della firma diventa un'uscita immediata, e che il messaggio dica
    all'utente la cosa che gli serve invece del solo errore della CLI."""
    assembla = _assembla()
    with pytest.raises(SystemExit) as uscita:
        assembla._verifica_firma(lambda: "Wrong password for that key")
    messaggio = str(uscita.value)
    assert "Wrong password" in messaggio
    assert "SINGOLI" in messaggio


def test_una_chiave_utilizzabile_non_ferma_niente():
    assembla = _assembla()
    assembla._verifica_firma(lambda: None)
