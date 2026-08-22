"""L'avvio legge il .env dalla cartella dei dati e si ferma con un messaggio
comprensibile se quella cartella non è scrivibile."""
import os
import stat
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.core import paths
from app.main import app


def test_dotenv_letto_dalla_cartella_dei_dati(tmp_path):
    """In un bundle `backend/` è di sola lettura: il .env deve stare coi dati.

    Subprocess e non monkeypatch: `env_file` si fissa alla definizione della
    classe Settings, quindi va provato il percorso d'avvio vero — che è poi
    quello che eseguirà Tauri.
    """
    (tmp_path / ".env").write_text("LOG_LEVEL=WARNING\n")
    ambiente = {k: v for k, v in os.environ.items() if k != "LOG_LEVEL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c",
         "from app.core.config import settings; print(settings.log_level)"],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr
    assert esito.stdout.strip() == "WARNING"


def test_avvio_con_cartella_non_scrivibile_dice_perche(monkeypatch, tmp_path):
    """Il messaggio è tutto ciò che l'utente di un'app impacchettata vedrà."""
    bloccata = tmp_path / "sola-lettura"
    bloccata.mkdir()
    bloccata.chmod(stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setattr(paths, "DATA_DIR", bloccata)
    try:
        with pytest.raises(RuntimeError) as errore:
            with TestClient(app):
                pass
        assert paths.DATA_DIR_ENV in str(errore.value)
        assert str(bloccata) in str(errore.value)
    finally:
        bloccata.chmod(stat.S_IRWXU)
