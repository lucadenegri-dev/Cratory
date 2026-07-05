"""Indicizzazione della libreria canonica (LIBRARY_ROOT)."""
import pytest

from app.core.config import Settings


def test_library_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.library_root == ""


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Crea file finti e monkeypatcha hash/tag/qualita' per renderli deterministici."""
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None, isrc=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": isrc,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


def test_riaggancio_per_audio_hash(db, fake_audio):
    """File rinominato/ritaggato: stesso hash ⇒ stessa Track, local_path aggiornato."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", spotify_id="s1", title="Origin", artist="A",
              has_local_file=True, local_path="/vecchio/inbox/file.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Techno/A/A - Origin.mp3", digest="H1")
    report = index_library(db, root=root)

    db.refresh(t)
    assert report["relinked"] == 1 and report["created"] == 0
    assert t.local_path.endswith("A - Origin.mp3")
    assert t.has_local_file is True and t.local_format == "mp3"


def test_match_per_isrc_da_tag(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", isrc="ISRC001", title="X", artist="A")
    db.add(t); db.commit()

    make("f.mp3", digest="H9", isrc="ISRC001")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True and t.audio_hash == "H9"


def test_match_fuzzy_artista_titolo(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="My Song", artist="Someone")
    db.add(t); db.commit()

    make("g.mp3", digest="H8", artist="someone", title="my song")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True


def test_file_sconosciuto_crea_track_local_files(db, fake_audio):
    from sqlalchemy import select
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    report = index_library(db, root=root)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"
    assert t.platform_track_id == "H7" and t.artist == "N"


def test_non_sovrascrive_identita_esistente(db, fake_audio):
    """I tag del file riempiono solo i campi vuoti (l'enrichment/manuale resta autorevole)."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Titolo Corretto", artist="A",
              genre="Techno", audio_hash="H1")
    db.add(t); db.commit()

    make("f.mp3", digest="H1", artist="A", title="titolo sbagliato dal tag")
    index_library(db, root=root)

    db.refresh(t)
    assert t.title == "Titolo Corretto" and t.genre == "Techno"


def test_duplicati_stesso_run_primo_vince(db, fake_audio):
    """Stesso audio in due file: il primo vince, il secondo si conta come duplicato."""
    from sqlalchemy import select
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    make("a.mp3", digest="HD", artist="A", title="Dup")
    make("b.mp3", digest="HD", artist="A", title="Dup")
    report = index_library(db, root=root)

    assert report["created"] == 1 and report["duplicates"] == 1
    assert report["relinked"] == 0
    t = db.scalar(select(Track).where(Track.audio_hash == "HD"))
    assert t.local_path.endswith("a.mp3")  # scan_folder ordina: il primo file vince


def test_riconciliazione_file_sparito(db, fake_audio, tmp_path):
    """Possesso orfano (file cancellato/spostato fuori) ⇒ torna wishlist, hash conservato."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    sparito = Track(source_type="spotify", title="Gone", artist="A",
                    has_local_file=True, local_path=str(tmp_path / "non-esiste.mp3"),
                    local_format="mp3", audio_hash="HGONE")
    db.add(sparito); db.commit()

    make("resta.mp3", digest="HSTAY", artist="B", title="Stay")
    report = index_library(db, root=root)

    db.refresh(sparito)
    assert report["lost"] == 1
    assert sparito.has_local_file is False and sparito.local_path is None
    assert sparito.audio_hash == "HGONE"


def test_riconciliazione_non_tocca_i_visti(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Here", artist="A", audio_hash="H1")
    db.add(t); db.commit()
    make("here.mp3", digest="H1")
    report = index_library(db, root=root)

    db.refresh(t)
    assert report["lost"] == 0 and t.has_local_file is True


def test_radice_vuota_non_azzera_i_possessi(db, fake_audio, tmp_path):
    """Anti-unmount: scan a zero file (root sbagliata/smontata) salta la riconciliazione."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Keep", artist="A",
              has_local_file=True, local_path=str(tmp_path / "sparito.mp3"),
              audio_hash="HK")
    db.add(t); db.commit()

    vuota = tmp_path / "radice-vuota"
    vuota.mkdir()
    report = index_library(db, root=vuota)

    db.refresh(t)
    assert report["lost"] == 0
    assert t.has_local_file is True  # nessuna riconciliazione su scan vuoto


def test_report_indice_contiene_created_ids(db, tmp_path, monkeypatch):
    """Il report espone gli id delle Track create: il chiamante (job in background)
    li usa per agire sulle tracce nuove appena indicizzate."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    p = tmp_path / "Libreria" / "A - Nuova.mp3"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    monkeypatch.setattr(li, "audio_hash", lambda _: "H-NEW")
    monkeypatch.setattr(li, "read_tags", lambda _: {
        "title": "Nuova", "artist": "A", "album": None, "year": None,
        "duration_seconds": 200, "isrc": None, "genre": None})
    monkeypatch.setattr(li, "read_audio_quality", lambda _: {"format": "mp3", "bitrate": 320})

    report = index_library(db, root=tmp_path / "Libreria")
    assert report["created"] == 1
    assert len(report["created_ids"]) == 1
