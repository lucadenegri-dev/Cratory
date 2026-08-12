"""Robustezza dell'indicizzazione: file volatili e commit incrementali.

Due garanzie: 1) un file che sparisce tra la scansione e lo stat() non uccide
il run (si salta e si conta come failed); 2) il progresso della scansione viene
committato a blocchi, così un crash a metà run non butta via tutto il lavoro
(stesso principio del job di analisi, che committa per traccia)."""
import pytest


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stesso pattern di test_library_index.py: file finti, hash/tag deterministici.
    In più si spegne analyze_file: 60 file finti non devono lanciare 60 decode."""
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


def test_file_sparito_tra_scan_e_stat_non_uccide_il_run(db, fake_audio, monkeypatch, collega_da_disco):
    """Un file cancellato tra la scansione e lo stat() si salta e si conta come
    failed: il run completa e gli altri file vengono indicizzati."""
    from app.services import library_index as li

    make, root = fake_audio
    make("lib/A - T1.mp3", digest="H1", artist="A", title="T1")
    ghost = make("lib/B - Ghost.mp3", digest="H2", artist="B", title="Ghost")

    original_scan = li.scan_folder

    def scan_poi_sparisce(folder):
        files = original_scan(folder)
        ghost.unlink()  # il file sparisce DOPO la scansione, PRIMA dello stat()
        return files

    monkeypatch.setattr(li, "scan_folder", scan_poi_sparisce)

    report = collega_da_disco(root)

    assert report["failed"] == 1
    assert any("Ghost" in e["path"] for e in report["errors"])
    assert report["created"] == 1        # l'altro file è stato indicizzato
    assert report["scanned"] == 2


def test_commit_incrementale_prima_della_riconciliazione(db, fake_audio, monkeypatch,
                                                         semina_indice_libreria):
    """Con molti file nuovi (> soglia) almeno un commit avviene DURANTE il loop
    di aggancio — quindi prima della riconciliazione finale (lost/orfani), che
    viene dopo il loop.

    La misura si ferma dentro il loop (quanti commit erano già avvenuti quando è
    stato agganciato l'ULTIMO file) e non guarda l'ordine commit/riconciliazione:
    ci sono due commit che avvengono comunque prima della riconciliazione anche
    con zero commit incrementali — quello in coda a `semina_indice_libreria` (è
    dello scanner, non dell'aggancio) e quello in coda a `collega_tracce` —, e
    contarli renderebbe il test vero per costruzione. Provato col sabotaggio:
    con `COMMIT_EVERY` enorme questo test deve fallire.
    """
    from app.services import library_index as li

    make, root = fake_audio
    for i in range(60):
        make(f"lib/A - T{i:03d}.mp3", digest=f"H{i:03d}", artist="A", title=f"T{i:03d}")

    semina_indice_libreria(root)

    commit_fatti = {"n": 0}
    original_commit = db.commit
    monkeypatch.setattr(db, "commit",
                        lambda: (commit_fatti.__setitem__("n", commit_fatti["n"] + 1),
                                 original_commit())[1])
    # Ogni file nuovo passa da qui (è il flusso completo del loop): l'ultimo a
    # scrivere lascia la fotografia dei commit visti fin dentro il loop.
    commit_all_ultimo_file = {"n": 0}
    original_hash = li.audio_hash

    def hash_spia(p):
        commit_all_ultimo_file["n"] = commit_fatti["n"]
        return original_hash(p)

    monkeypatch.setattr(li, "audio_hash", hash_spia)
    original_unref = li.unreferenced_track_ids
    riconciliato = {"si": False}
    monkeypatch.setattr(li, "unreferenced_track_ids",
                        lambda *a, **k: (riconciliato.__setitem__("si", True),
                                         original_unref(*a, **k))[1])

    seen_paths: set[str] = set()
    report = li.collega_tracce(db, seen_paths=seen_paths, seen_digests=set())
    li.riconcilia_possessi(db, seen_paths=seen_paths, scanned=report["scanned"])

    assert report["created"] == 60
    assert riconciliato["si"]
    # Almeno un commit incrementale mentre il loop era ancora in corso.
    assert commit_all_ultimo_file["n"] >= 1


def test_commit_incrementale_progresso_sopravvive_a_crash(db, fake_audio, monkeypatch, collega_da_disco):
    """Crash simulato a metà scansione: i blocchi già committati restano nel DB
    (il lavoro non committato si perde, ma non tutto il run)."""
    from app.models import Track
    from app.services import library_index as li

    make, root = fake_audio
    for i in range(60):
        make(f"lib/A - T{i:03d}.mp3", digest=f"H{i:03d}", artist="A", title=f"T{i:03d}")

    original_hash = li.audio_hash
    calls = {"n": 0}

    def hash_poi_crash(p):
        calls["n"] += 1
        if calls["n"] > 55:
            raise RuntimeError("boom: crash simulato a metà scansione")
        return original_hash(p)

    monkeypatch.setattr(li, "audio_hash", hash_poi_crash)

    with pytest.raises(RuntimeError):
        collega_da_disco(root)
    db.rollback()  # scarta il lavoro non committato: resta solo il persistito

    persistite = db.query(Track).filter(Track.has_local_file.is_(True)).count()
    assert 50 <= persistite < 60  # i blocchi committati sopravvivono al crash
