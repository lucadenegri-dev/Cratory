"""Lo strumento di pulizia dei dati utente deve svuotare davvero il database.

Stessa famiglia dei difetti di `test_download_queue_track_lifecycle.py`: le
foreign key sono accese in produzione e nessuna delle tabelle figlie di `tracks`
ha ON DELETE CASCADE, quindi una `DELETE FROM tracks` che non sia stata preceduta
dalla cancellazione dei figli va in IntegrityError. Qui il figlio nuovo e'
`download_queue_items` (lo storico della coda, che resta finche' l'utente non lo
svuota); quello vecchio e' `playlist_tracks`, che non e' mai stato nell'elenco.

Il modulo lavora sull'engine globale di `app.db`, non sulla fixture `db`: i test
gliene sostituiscono uno tutto loro su file (VACUUM non gira in memoria).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DownloadQueueItem, Playlist, Track, playlist_tracks
from app.organize.models import AudioFile, ScanRoot
from app.tools import clean_user_data


@pytest.fixture()
def db_su_file(tmp_path, monkeypatch):
    """Engine su file temporaneo, montato al posto di quello globale.

    `clean` chiama `ensure_schema()` (che userebbe l'engine di modulo) e legge
    `settings.database_url` per il path: si sostituiscono entrambi, cosi' il test
    non tocca ne' il DB reale ne' quello condiviso dalla suite.
    """
    path = tmp_path / "clean.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(clean_user_data, "engine", engine)
    monkeypatch.setattr(clean_user_data, "ensure_schema", lambda: None)
    monkeypatch.setattr(clean_user_data.settings, "database_url", f"sqlite:///{path}")
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _semina(db):
    t = Track(source_type="spotify", title="T", artist="A")
    pl = Playlist(platform="spotify", name="P", kind="playlist")
    db.add_all([t, pl])
    db.flush()
    db.execute(playlist_tracks.insert().values(playlist_id=pl.id, track_id=t.id))
    db.add(DownloadQueueItem(track_id=t.id, kind="soulseek_auto", state="done",
                             outcome="downloaded", position=0))
    # Il quarto figlio di `tracks`: Organize aggancia i file scansionati alla
    # traccia via `audio_file.track_id`. E' lo stato normale di un'installazione
    # (`organize/services/file_link.py` lo popola), quindi va seminato anche qui.
    root = ScanRoot(path="/lib")
    db.add(root)
    db.flush()
    db.add(AudioFile(root_id=root.id, track_id=t.id, path="/lib/t.mp3", ext="mp3",
                     size_bytes=1, hash_method="sha1"))
    db.commit()
    return t, pl


def test_pulizia_libreria_svuota_anche_i_figli_di_tracks(db_su_file):
    """Con una membership playlist, uno storico di coda e un file Organize
    agganciato, la pulizia deve completare e lasciare il database vuoto —
    tranne `audio_file`, che non e' dato Cratory: va solo sganciato."""
    _semina(db_su_file)

    report = clean_user_data.clean("library", preserve_tokens=True,
                                   include_backups=False, dry_run=False)

    assert report["after"]["tracks"] == 0
    for tabella in ("tracks", "playlists", "playlist_tracks", "download_queue_items"):
        resto = db_su_file.execute(text(f"SELECT COUNT(*) FROM {tabella}")).scalar_one()
        assert resto == 0, f"{tabella} non e' stata svuotata"
    # audio_file resta (fuori perimetro di questo strumento) ma sganciata.
    assert db_su_file.execute(
        text("SELECT COUNT(*) FROM audio_file")).scalar_one() == 1
    assert db_su_file.execute(
        text("SELECT track_id FROM audio_file")).scalar_one() is None


def test_dry_run_non_cancella_nulla(db_su_file):
    """Il conteggio `before` deve essere reale anche in dry-run, e il DB intatto."""
    _semina(db_su_file)

    report = clean_user_data.clean("library", preserve_tokens=True,
                                   include_backups=False, dry_run=True)

    assert report["before"]["tracks"] == 1
    assert db_su_file.execute(text("SELECT COUNT(*) FROM tracks")).scalar_one() == 1
    assert db_su_file.execute(
        text("SELECT COUNT(*) FROM download_queue_items")).scalar_one() == 1
