"""Il file di configurazione è dell'utente, non nostro: scriverci dentro non
deve fargli perdere niente."""
import os
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from app.services import slskd_daemon as sd

ESISTENTE = """\
# La mia configurazione, scritta a mano
soulseek:
  username: vecchio
  password: vecchia
  description: "Ciao dal mio slskd"
shares:
  directories:
    - /Users/io/Musica
web:
  port: 5030
  authentication:
    api_keys:
      cratory:
        key: abc123
"""


def _carica(p: Path) -> dict:
    return YAML().load(p.read_text())


def test_le_chiavi_non_nostre_sopravvivono(tmp_path):
    """L'invariante che protegge la configurazione dell'utente: si verifica
    sul contenuto integrale, non sulle quattro chiavi che tocchiamo."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="nuovo", password="nuova",
                    port=5030, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["description"] == "Ciao dal mio slskd"
    assert data["shares"]["directories"] == ["/Users/io/Musica"]
    assert data["web"]["authentication"]["api_keys"]["cratory"]["key"] == "abc123"


def test_le_chiavi_nostre_vengono_aggiornate(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="nuovo", password="nuova",
                    port=5031, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["username"] == "nuovo"
    assert data["soulseek"]["password"] == "nuova"
    assert data["web"]["port"] == 5031
    assert data["directories"]["downloads"] == "/tmp/dl"


def test_i_commenti_sopravvivono(tmp_path):
    """ruamel in round-trip li preserva: se qualcuno passasse a PyYAML,
    l'utente perderebbe i propri commenti senza accorgersene."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert "# La mia configurazione, scritta a mano" in cfg.read_text()


def test_config_assente_viene_creata(tmp_path):
    cfg = tmp_path / "nuova" / "slskd.yml"
    sd.write_config(cfg, username="io", password="segreta",
                    port=5030, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["username"] == "io"


ESISTENTE_CON_PORTA_E_CARTELLA_CUSTOM = """\
soulseek:
  username: vecchio
  password: vecchia
web:
  port: 6033
directories:
  downloads: /mio/download/custom
"""


def test_campi_omessi_lasciano_intatto_quel_che_gia_c_e(tmp_path):
    """Il finding critico: una richiesta che tocca solo le credenziali non
    deve toccare porta e cartella download gia' scelte dall'utente. `None`
    (campo omesso) non e' un valore, e' l'assenza di uno: write_config deve
    lasciare stare quel che trova nel file, non riscriverlo col default."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE_CON_PORTA_E_CARTELLA_CUSTOM)

    sd.write_config(cfg, username="nuovo", password="nuova", port=None, download_dir=None)

    data = _carica(cfg)
    assert data["soulseek"]["username"] == "nuovo"
    assert data["soulseek"]["password"] == "nuova"
    assert data["web"]["port"] == 6033
    assert data["directories"]["downloads"] == "/mio/download/custom"


def test_campi_omessi_su_file_nuovo_prendono_i_default(tmp_path, monkeypatch):
    """Al primo setup il file non esiste: qui, e SOLO qui, un campo omesso
    deve prendere un valore di default (deve pur venire da qualche parte)."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_download_dir", lambda: "/default/dl")
    cfg = tmp_path / "nuova" / "slskd.yml"
    sd.write_config(cfg, username="io", password="segreta", port=None, download_dir=None)
    data = _carica(cfg)
    assert data["web"]["port"] == sd.DEFAULT_PORT
    assert data["directories"]["downloads"] == "/default/dl"


def test_il_file_non_e_leggibile_da_altri(tmp_path):
    """Contiene la password Soulseek in chiaro: è così che funziona slskd,
    ma i permessi devono almeno rifletterlo."""
    import stat as st
    cfg = tmp_path / "slskd.yml"
    sd.write_config(cfg, username="io", password="segreta",
                    port=5030, download_dir="/tmp/dl")
    assert st.S_IMODE(cfg.stat().st_mode) == 0o600


def test_il_backup_conserva_l_originale(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert cfg.with_suffix(".yml.bak").read_text() == ESISTENTE


def test_il_backup_non_e_leggibile_da_altri(tmp_path):
    """Il finding M1: `.bak` contiene la stessa password in chiaro del file
    vero, ma veniva scritto con `Path.write_text()`, che rispetta l'umask
    invece dei permessi del file che sta duplicando — 0o644 con un umask
    tipico, world-readable, dodici righe dopo che il file vero viene
    ristretto apposta a 0o600. La password finiva leggibile lo stesso, solo
    da un file diverso."""
    import stat as st
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    os.chmod(cfg, 0o600)  # come lo lascerebbe una write_config precedente
    sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert st.S_IMODE(cfg.with_suffix(".yml.bak").stat().st_mode) == 0o600


def test_cartella_download_vuota_su_file_nuovo_non_scrive_stringa_vuota(tmp_path, monkeypatch):
    """Stesso momento di `test_campi_omessi_su_file_nuovo_prendono_i_default`,
    ma senza un default già in `runtime_settings`: `slskd_download_dir()`
    vuota (il caso reale di un primo setup su cui l'utente non ha ancora
    scelto una cartella) non deve finire scritta cosi' com'e' in
    `directories.downloads` — slskd partirebbe con una cartella di download
    vuota, non assente."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_download_dir", lambda: "")
    # Non deve toccare la vera backend/data/: isolata come pid_file/log_file
    # nelle fixture degli altri test di questo modulo.
    monkeypatch.setattr(sd, "_cartella_download_default", lambda: tmp_path / "download-default")
    cfg = tmp_path / "nuova" / "slskd.yml"
    esito = sd.write_config(cfg, username="io", password="segreta", port=None, download_dir=None)
    data = _carica(cfg)
    assert data["directories"]["downloads"], "non deve restare vuota"
    assert Path(data["directories"]["downloads"]).is_dir(), "la cartella proposta deve esistere davvero"
    assert esito.download_dir == data["directories"]["downloads"]


def test_config_written_riporta_cosa_e_stato_scelto_su_file_nuovo(tmp_path, monkeypatch):
    """`ConfigWritten` è quello che il router userà per allineare le
    impostazioni di Cratory (finding B2): deve riportare `created=True` e i
    valori EFFETTIVAMENTE scritti, non semplicemente eco degli argomenti
    (che qui sono `None`)."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_download_dir", lambda: "/scelta/utente")
    cfg = tmp_path / "nuova" / "slskd.yml"
    esito = sd.write_config(cfg, username="io", password="segreta", port=None, download_dir=None)
    assert esito.created is True
    assert esito.port == sd.DEFAULT_PORT
    assert esito.download_dir == "/scelta/utente"


def test_config_written_su_file_esistente_non_e_creato(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    esito = sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert esito.created is False


def test_rilettura_dell_username(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    assert sd.read_username(cfg) == "vecchio"


def test_rilettura_su_file_assente(tmp_path):
    assert sd.read_username(tmp_path / "manca.yml") is None


# La chiave API: senza, slskd risponde 401 a ogni chiamata di Cratory.

SENZA_CHIAVE = """\
soulseek:
  username: vecchio
  password: vecchia
web:
  port: 5030
"""


def test_la_chiave_api_viene_creata_quando_manca(tmp_path):
    """Il bug del 401 su installazione fresca: `write_config` scriveva
    credenziali Soulseek, porta e cartella download, ma nessuna chiave API —
    e slskd rifiuta ogni `/api/v0/*` senza. L'utente arrivava fino a
    "Connetti" e prendeva un 401 da un demone che aveva appena avviato con
    successo, perché `/health` (l'unica cosa che Cratory guardava per dirlo
    "raggiungibile") è anonimo e il resto no."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(SENZA_CHIAVE)
    esito = sd.write_config(cfg, username="io", password="segreta",
                            port=5030, download_dir="/tmp/dl")
    voce = _carica(cfg)["web"]["authentication"]["api_keys"][sd.API_KEY_NAME]
    assert voce["key"] == esito.api_key
    assert len(voce["key"]) >= 16, "slskd rifiuta le chiavi più corte di 16 caratteri"
    assert voce["role"] == "Administrator", "PUT /server e PUT /shares vogliono l'admin"


def test_la_chiave_api_esistente_viene_riusata(tmp_path):
    """Rigenerarla ad ogni salvataggio romperebbe chi una chiave ce l'ha già
    (scritta a mano, magari anche incollata nelle impostazioni): si riusa e
    si riporta al chiamante, che deve poterla specchiare in `slskd_api_key`."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    esito = sd.write_config(cfg, username="n", password="p",
                            port=5030, download_dir="/tmp/dl")
    assert esito.api_key == "abc123"
    assert _carica(cfg)["web"]["authentication"]["api_keys"]["cratory"]["key"] == "abc123"


def test_ogni_installazione_ha_la_sua_chiave(tmp_path):
    """Una chiave costante sarebbe una password pubblicata su GitHub: chiunque
    altro sulla macchina potrebbe comandare il demone dell'utente."""
    a = sd.write_config(tmp_path / "a" / "slskd.yml", username="io", password="p",
                        port=5030, download_dir="/tmp/dl")
    b = sd.write_config(tmp_path / "b" / "slskd.yml", username="io", password="p",
                        port=5030, download_dir="/tmp/dl")
    assert a.api_key != b.api_key


def test_authentication_presente_ma_vuota(tmp_path):
    """`authentication:` senza figli è `None` in YAML, non un dizionario: un
    `setdefault` ci si romperebbe sopra con un AttributeError, su un file
    perfettamente legittimo."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: vecchio\nweb:\n  port: 5030\n  authentication:\n")
    esito = sd.write_config(cfg, username="io", password="p",
                            port=5030, download_dir="/tmp/dl")
    voce = _carica(cfg)["web"]["authentication"]["api_keys"][sd.API_KEY_NAME]
    assert voce["key"] == esito.api_key


def test_ensure_api_key_non_chiede_le_credenziali(tmp_path):
    """La riparazione di chi ha configurato slskd PRIMA che Cratory scrivesse
    la chiave: la password Soulseek è entrata e non esce più (non la si
    rilegge né la si richiede), quindi la chiave dev'essere aggiungibile
    senza toccare nient'altro del file."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(SENZA_CHIAVE)
    chiave = sd.ensure_api_key(cfg)
    data = _carica(cfg)
    assert data["soulseek"]["username"] == "vecchio"
    assert data["soulseek"]["password"] == "vecchia"
    assert data["web"]["port"] == 5030
    assert data["web"]["authentication"]["api_keys"][sd.API_KEY_NAME]["key"] == chiave


def test_ensure_api_key_e_idempotente(tmp_path):
    """Ripararlo due volte non deve invalidare la chiave che la prima
    riparazione ha appena messo nelle impostazioni."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(SENZA_CHIAVE)
    assert sd.ensure_api_key(cfg) == sd.ensure_api_key(cfg)


def test_ensure_api_key_conserva_permessi_e_backup(tmp_path):
    """Riscrive lo stesso file che contiene la password in chiaro: stessa
    cautela di `write_config`, non una scorciatoia."""
    import stat as st
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(SENZA_CHIAVE)
    os.chmod(cfg, 0o600)
    sd.ensure_api_key(cfg)
    assert st.S_IMODE(cfg.stat().st_mode) == 0o600
    assert cfg.with_suffix(".yml.bak").read_text() == SENZA_CHIAVE


def test_ensure_api_key_senza_file(tmp_path):
    """Non c'è niente da riparare: senza credenziali Soulseek un file di sola
    chiave API farebbe partire un demone che non si collega a nulla. Chi
    chiama deve poter distinguere questo caso e rimandare alla configurazione."""
    with pytest.raises(sd.ConfigMissing):
        sd.ensure_api_key(tmp_path / "manca.yml")
