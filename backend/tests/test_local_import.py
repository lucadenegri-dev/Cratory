"""Import da cartella locale: scansione, fallback nome file, idempotenza, separazione tracce."""

import math
import struct
import wave

import pytest

from app.models import Playlist, Track
from app.services.local_import import import_local_folder, scan_folder


def _write_wav(path, *, freq: int = 440, secs: float = 0.5, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        )
        w.writeframes(frames)


def _tag_wav(path, *, title=None, artist=None) -> None:
    from mutagen.id3 import TIT2, TPE1
    from mutagen.wave import WAVE

    w = WAVE(str(path))
    if w.tags is None:
        w.add_tags()
    if title:
        w.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        w.tags.add(TPE1(encoding=3, text=[artist]))
    w.save()


def test_scan_folder_ricorsivo_ignora_non_audio(tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_wav(sub / "b.wav", freq=660)
    (tmp_path / "note.txt").write_text("x")
    found = scan_folder(tmp_path, recurse=True)
    names = sorted(p.name for p in found)
    assert names == ["a.wav", "b.wav"]


def test_import_usa_fallback_nome_file(db, tmp_path):
    p = tmp_path / "Daft Punk - Da Funk.wav"
    _write_wav(p, freq=440)  # nessun tag
    report = import_local_folder(db, path=tmp_path, name="Crate")
    assert report["created"] == 1
    t = db.query(Track).first()
    assert t.artist == "Daft Punk"
    assert t.title == "Da Funk"
    assert t.source_type == "local_files"
    assert t.platform == "local_files"


def test_riscansione_idempotente(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _tag_wav(tmp_path / "a.wav", title="A", artist="X")
    r1 = import_local_folder(db, path=tmp_path, name="Crate")
    r2 = import_local_folder(db, path=tmp_path, name="Crate")
    assert r1["created"] == 1
    assert r2["created"] == 0
    assert r2["updated"] == 1
    assert db.query(Track).count() == 1


def test_riscansione_riusa_stessa_playlist(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _tag_wav(tmp_path / "a.wav", title="A", artist="X")
    r1 = import_local_folder(db, path=tmp_path, name="Crate")
    r2 = import_local_folder(db, path=tmp_path, name="Crate")
    assert r1["playlist_id"] == r2["playlist_id"]  # stessa cartella -> stessa playlist
    assert db.query(Playlist).count() == 1  # nessun doppione di playlist


def test_file_rimosso_viene_scollegato_dalla_playlist(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _tag_wav(tmp_path / "a.wav", title="A", artist="X")
    _write_wav(tmp_path / "b.wav", freq=880)
    _tag_wav(tmp_path / "b.wav", title="B", artist="Y")
    r1 = import_local_folder(db, path=tmp_path, name="Crate")
    pid = r1["playlist_id"]
    assert db.query(Track).count() == 2
    (tmp_path / "b.wav").unlink()  # il file sparisce dalla cartella
    r2 = import_local_folder(db, path=tmp_path, name="Crate")
    assert r2["removed"] == 1
    pl = db.get(Playlist, pid)
    assert pl.track_count == 1  # la playlist riflette la cartella
    assert db.query(Track).count() == 2  # la traccia resta comunque in libreria


def test_file_rinominato_aggiorna_path_senza_duplicare(db, tmp_path):
    a = tmp_path / "a.wav"
    _write_wav(a, freq=440)
    _tag_wav(a, title="A", artist="X")
    import_local_folder(db, path=tmp_path, name="Crate")
    a.rename(tmp_path / "renamed.wav")  # stesso audio -> stesso hash
    import_local_folder(db, path=tmp_path, name="Crate")
    assert db.query(Track).count() == 1
    assert db.query(Track).first().local_path.endswith("renamed.wav")


def test_due_file_audio_diversi_stesso_nome_brano_due_tracce(db, tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_wav(a, freq=440)
    _write_wav(b, freq=880)  # audio diverso -> hash diverso
    _tag_wav(a, title="Stesso", artist="Brano")
    _tag_wav(b, title="Stesso", artist="Brano")
    report = import_local_folder(db, path=tmp_path, name="Crate")
    assert report["created"] == 2  # identità per hash, non per nome
    assert db.query(Track).count() == 2


def test_non_si_fonde_con_traccia_spotify_omonima(db, tmp_path):
    db.add(Track(source_type="spotify", platform="spotify", platform_track_id="sp1",
                 title="Da Funk", artist="Daft Punk"))
    db.commit()
    p = tmp_path / "x.wav"
    _write_wav(p, freq=440)
    _tag_wav(p, title="Da Funk", artist="Daft Punk")
    import_local_folder(db, path=tmp_path, name="Crate")
    assert db.query(Track).count() == 2  # crea una traccia locale distinta
    assert db.query(Track).filter_by(source_type="local_files").count() == 1
    assert db.query(Track).filter_by(source_type="spotify").count() == 1


def test_cartella_vuota_non_crea_playlist(db, tmp_path):
    report = import_local_folder(db, path=tmp_path, name="Vuota")
    assert report["total"] == 0
    assert report["playlist_id"] is None


def test_progress_callback_invocato(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _write_wav(tmp_path / "b.wav", freq=660)
    seen = []
    import_local_folder(db, path=tmp_path, name="Crate",
                        on_progress=lambda p, t: seen.append((p, t)))
    assert seen[-1] == (2, 2)
