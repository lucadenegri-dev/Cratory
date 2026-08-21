"""Il file di configurazione è dell'utente, non nostro: scriverci dentro non
deve fargli perdere niente."""
from pathlib import Path

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


def test_rilettura_dell_username(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    assert sd.read_username(cfg) == "vecchio"


def test_rilettura_su_file_assente(tmp_path):
    assert sd.read_username(tmp_path / "manca.yml") is None
