"""E2: il ramo archivio 'file ignoto' (nessuna traccia da scartare, si ricorda
solo la firma in ArchiveSeen) chiama path.stat() senza guardia: un file che
sparisce/diventa illeggibile tra l'audio_hash e lo stat() non deve uccidere
il run, va saltato e contato come failed (stesso principio della passata 1)."""
import pytest


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stesso pattern di test_library_index_robustness.py: file finti, hash/tag
    deterministici, analyze_file spento."""
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

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve())])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve())])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    monkeypatch.setattr(li, "analyze_file", lambda p, d=None: None)
    return make, tmp_path


def test_file_archivio_ignoto_sparito_prima_dello_stat_non_uccide_il_run(
        db, fake_audio, monkeypatch, semina_indice_libreria):
    """Un file d'archivio senza traccia da scartare che sparisce tra l'hash e lo
    stat() (usato solo per popolare ArchiveSeen) si salta e si conta come failed:
    il run completa e gli altri file d'archivio/libreria vengono comunque gestiti."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()

    make("Libreria/A - T1.mp3", digest="H1", artist="A", title="T1")
    ghost = make("Archived/B - Ghost.mp3", digest="H2", artist="B", title="Ghost")

    original_scan = li.scan_folder

    def scan_poi_sparisce(folder):
        files = original_scan(folder)
        if str(folder) == str(arc):
            ghost.unlink()  # sparisce DOPO la scansione, PRIMA dello stat() nel ramo archivio
        return files

    monkeypatch.setattr(li, "scan_folder", scan_poi_sparisce)

    # `index_library` non cammina più `lib`: lo semina prima, come farebbe lo
    # scanner di Organize, così `collega_tracce` trova la riga per T1.
    semina_indice_libreria(lib)
    report = index_library(db, root=lib, archive_root=arc)

    assert report["failed"] == 1
    assert any("Ghost" in e["path"] for e in report["errors"])
    assert report["created"] == 1        # il file in libreria è stato comunque indicizzato
    assert report["archived"] == 0       # nessuna traccia da scartare per il file fantasma


def test_file_archivio_ignoto_ok_registra_ancora_la_firma(db, fake_audio):
    """Contro-prova: senza il guasto, il comportamento esistente resta invariato
    (nessuna regressione sul percorso felice)."""
    from app.models import ArchiveSeen
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    make("Archived/Sconosciuto - Boh.mp3", digest="H-IGNOTO")

    report = index_library(db, root=lib, archive_root=arc)

    assert report["failed"] == 0
    assert report["created"] == 0 and report["archived"] == 0
    assert db.query(ArchiveSeen).count() == 1
