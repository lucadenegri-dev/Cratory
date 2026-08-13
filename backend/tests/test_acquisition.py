from sqlalchemy import select

from app.models import Track
from app.repositories import tracks_without_local_file
from app.services.acquisition import attach_local_file


def test_attach_local_file_sets_ownership_fields(db):
    t = Track(platform="spotify", spotify_id="s1", source_type="spotify",
              title="Da Funk", artist="Daft Punk", status="imported")
    db.add(t)
    db.commit()
    attach_local_file(db, t, path="/music/x.flac", fmt="flac", bitrate=1000)
    db.refresh(t)
    assert t.has_local_file is True
    assert t.local_path == "/music/x.flac"
    assert t.local_format == "flac"
    assert t.local_bitrate == 1000
    # lo status di enrichment NON viene toccato
    assert t.status == "imported"


def test_tracks_without_local_file_filters(db):
    from app.models import Playlist
    from app.repositories import add_track_to_playlist

    pl = Playlist(name="PL", platform="spotify", platform_playlist_id="pl1", kind="spotify")
    db.add(pl)
    db.commit()
    owned = Track(platform="spotify", spotify_id="o", source_type="spotify",
                  title="A", artist="X", has_local_file=True)
    missing = Track(platform="spotify", spotify_id="m", source_type="spotify",
                    title="B", artist="Y")
    db.add_all([owned, missing])
    db.commit()
    add_track_to_playlist(db, owned, pl)
    add_track_to_playlist(db, missing, pl)
    db.commit()
    result = tracks_without_local_file(db, pl.id)
    ids = {t.spotify_id for t in result}
    assert ids == {"m"}


def test_attach_salva_audio_hash(db, monkeypatch):
    from app.models import Track
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "abc123")
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3", fmt="mp3", bitrate=320)
    assert out.audio_hash == "abc123"
    assert out.has_local_file is True


def test_attach_salva_mtime_e_size(db, tmp_path, monkeypatch):
    """Il collegamento memorizza la firma del file (mtime+size): senza, il prossimo
    indice incrementale non puo' skipparlo e lo ri-hasha (decodifica ffmpeg)."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HMS")
    f = tmp_path / "song.mp3"
    f.write_bytes(b"finto audio")
    t = Track(source_type="spotify")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path=str(f), fmt="mp3", bitrate=320)

    stat = f.stat()
    assert out.local_mtime == stat.st_mtime
    assert out.local_size == stat.st_size


def test_attach_stat_fallito_non_blocca(db, monkeypatch):
    """File non stat-abile (path sparito tra download e attach): il possesso resta,
    la firma incrementale semplicemente non c'e'."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HNS")
    t = Track(source_type="spotify")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/non/esiste/y.mp3", fmt="mp3")

    assert out.has_local_file is True
    assert out.local_mtime is None
    assert out.local_size is None


def test_attach_hash_fallito_non_blocca(db, monkeypatch):
    from app.integrations.local_files import LocalFilesError
    from app.models import Track
    from app.services import acquisition

    def boom(p):
        raise LocalFilesError("ffmpeg assente")

    monkeypatch.setattr(acquisition, "audio_hash", boom)
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3")
    assert out.has_local_file is True
    assert out.audio_hash is None


def _indicizza(db, path: str, *, genre: str | None) -> None:
    """Un file gia' scansionato da Organize a quel path (cosi' `aggiorna_primary`
    lo trova e l'aggancio nasce con un primary file)."""
    from app.organize.models import AudioFile, ScanRoot

    root = db.scalar(select(ScanRoot).where(ScanRoot.path == "/m"))
    if root is None:
        root = ScanRoot(path="/m")
        db.add(root)
        db.flush()
    db.add(AudioFile(root_id=root.id, path=path, ext="mp3", size_bytes=1,
                     hash_method="file", status="present", location="library",
                     genre=genre))
    db.commit()


def test_acquisizione_allinea_il_genere_al_tag_del_file(db, monkeypatch):
    """Stessa classe di D8, sul percorso dell'acquisizione (Soulseek, download
    SoundCloud, collegamento manuale): un lead che arriva con un genere
    streaming e acquisisce un file gia' indicizzato da Organize terrebbe quel
    genere per sempre. Lo scan non ripara: la riga AudioFile e' stata INSERITA,
    non aggiornata, quindi la sua guardia (`fields["genre"] != old_genre`) non
    scatta mai per quel file."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HG1")
    _indicizza(db, "/m/a.mp3", genre="Techno")
    t = Track(source_type="spotify", title="X", artist="A", genre="Electronic")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/m/a.mp3", fmt="mp3", bitrate=320)

    assert out.primary_file_id is not None  # l'aggancio c'e' davvero
    assert out.genre == "Techno"


def test_acquisizione_senza_file_indicizzato_non_tocca_il_genere(db, monkeypatch):
    """Organize non ha ancora scansionato quel path: niente primary file, niente
    da allineare. Il possesso resta valido e il genere streaming intatto — al
    prossimo scan ci pensa la sincronizzazione normale."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HG2")
    t = Track(source_type="spotify", title="X", artist="A", genre="Electronic")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/mai/scansionato.mp3", fmt="mp3")

    assert out.primary_file_id is None
    assert out.genre == "Electronic"
    assert out.has_local_file is True


def test_acquisizione_tag_vuoto_non_azzera_il_genere(db, monkeypatch):
    """Il file e' indicizzato ma senza tag genere: la regola condivisa non
    sovrascrive mai con il vuoto (il valore streaming resta l'unico che c'e')."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HG3")
    _indicizza(db, "/m/b.mp3", genre=None)
    t = Track(source_type="spotify", title="X", artist="A", genre="Electronic")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/m/b.mp3", fmt="mp3")

    assert out.primary_file_id is not None
    assert out.genre == "Electronic"


def test_acquisizione_non_tocca_identita_ne_altri_campi(db, monkeypatch):
    """Perimetro: solo `genre`. Titolo, artista, album, etichetta e anno della
    traccia restano quelli di Cratory anche se il file dice altro."""
    from app.organize.models import AudioFile
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HG4")
    _indicizza(db, "/m/c.mp3", genre="Techno")
    f = db.scalar(select(AudioFile).where(AudioFile.path == "/m/c.mp3"))
    f.artist, f.title, f.album, f.label, f.year = "File A", "File T", "File Alb", "File Lab", 1999
    db.commit()
    t = Track(source_type="spotify", title="Titolo", artist="Artista", genre="Electronic",
              album="Album", label="Etichetta", year=2020)
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/m/c.mp3", fmt="mp3")

    assert out.genre == "Techno"
    assert (out.title, out.artist) == ("Titolo", "Artista")
    assert (out.album, out.label, out.year) == ("Album", "Etichetta", 2020)
