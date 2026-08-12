"""Uno scan solo produce l'indice dei file E le tracce."""

import shutil

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.roots import radici
from app.organize.services.scanner import scan


def test_uno_scan_produce_indice_e_tracce(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    summary = scan(db, [radici(db)["library"]])
    db.commit()

    assert summary.inserted == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None
    assert summary.linking is not None and summary.linking["created"] == 1


def test_le_fasi_sono_riportate_al_progresso(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    fasi = []
    scan(db, [radici(db)["library"]], on_progress=lambda p, t, phase: fasi.append(phase))
    db.commit()

    assert "scanning" in fasi
    assert "linking" in fasi


def test_il_secondo_scan_non_cambia_nulla(db, fake_audio, monkeypatch):
    """Idempotenza: è la milestone della fase."""
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    scan(db, [radici(db)["library"]])
    db.commit()
    secondo = scan(db, [radici(db)["library"]])
    db.commit()

    assert secondo.inserted == 0
    assert secondo.linking["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1


def test_scan_ricalcola_energia(db, fake_audio, monkeypatch):
    """`index_library` non è tre chiamate ma quattro: chiude con
    `recompute_energy`, che calibra `energy_raw` (scritto da `_own`) in `energy`
    (0-100). Lo scanner deve chiudere la stessa sequenza, non fermarsi alla
    terza, o le Track appena agganciate restano con `energy` NULL."""
    from app.core.config import settings
    from app.services import library_index as li

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "archive_root", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    calls: list[int] = []
    monkeypatch.setattr(li, "recompute_energy", lambda db: calls.append(1) or 3)

    summary = scan(db, [radici(db)["library"]])
    db.commit()

    assert calls == [1]
    assert summary.linking["energy_computed"] == 3


def test_scan_non_ricalcola_energia_su_indice_vuoto(db, fake_audio, monkeypatch):
    """Anti-unmount, come `index_library`: uno scan che non vede righe di
    libreria (radice smontata o vuota) non deve ricalcolare l'energia."""
    from app.core.config import settings
    from app.services import library_index as li

    _, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "archive_root", "")

    calls: list[int] = []
    monkeypatch.setattr(li, "recompute_energy", lambda db: calls.append(1) or 0)

    vuota = root / "radice-vuota"
    vuota.mkdir()
    summary = scan(db, [radici(db)["library"]])
    db.commit()

    assert calls == []
    assert "energy_computed" not in summary.linking


def _cfg(monkeypatch, lib, arc):
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", str(lib))
    monkeypatch.setattr(settings, "archive_root", str(arc))
    monkeypatch.setattr(settings, "slskd_download_dir", "")


def test_possesso_vince_sull_archivio(db, fake_audio, monkeypatch):
    make, root = fake_audio
    lib, arc = root / "lib", root / "arc"
    _cfg(monkeypatch, lib, arc)
    make("lib/a.mp3", digest="H1", artist="A", title="A")
    make("arc/a.mp3", digest="H1", artist="A", title="A")

    summary = scan(db, [radici(db)["library"]])
    db.commit()

    t = db.scalar(select(Track).where(Track.audio_hash == "H1"))
    assert t is not None and t.has_local_file is True and not t.archived
    assert summary.linking["duplicates"] == 1


def test_file_passato_in_archivio_e_scartato_non_cancellato(db, fake_audio, monkeypatch):
    make, root = fake_audio
    lib, arc = root / "lib", root / "arc"
    _cfg(monkeypatch, lib, arc)
    p = make("lib/b.mp3", digest="H2", artist="B", title="B")
    scan(db, [radici(db)["library"]])
    db.commit()

    p.unlink()
    make("arc/b.mp3", digest="H2", artist="B", title="B")
    summary = scan(db, [radici(db)["library"]])
    db.commit()

    t = db.scalar(select(Track).where(Track.audio_hash == "H2"))
    assert t is not None, "traccia CANCELLATA invece che marcata scartata"
    assert t.archived is True
    assert summary.linking["archived"] == 1
    assert summary.linking["orphans_removed"] == 0


def _due_radici(monkeypatch, lib, inbox):
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", str(lib))
    monkeypatch.setattr(settings, "slskd_download_dir", str(inbox))
    monkeypatch.setattr(settings, "archive_root", "")


def test_radice_smontata_non_cancella_le_tracce(db, fake_audio, monkeypatch):
    """Anti-unmount: la fase 2 deve VEDERE il `missing` scritto dalla fase 1.

    `SessionLocal` è `autoflush=False` e la SELECT di `collega_tracce` filtra
    sul DB, non sulla Session: senza un flush esplicito dopo `_reconcile` le
    righe di una radice smontata risultano ancora `present`, `scanned` non è
    zero, la guardia anti-unmount di `riconcilia_possessi` non scatta e ogni
    possesso viene classificato perso — le tracce non referenziate finiscono
    cancellate. Innesco realistico: disco esterno non montato al boot, più
    l'avvio automatico dello scan nel lifespan.
    """
    make, root = fake_audio
    lib = root / "lib"
    _due_radici(monkeypatch, lib, root / "inbox")
    make("lib/a.mp3", digest="H1", artist="A", title="A")

    percorse = list(radici(db).values())
    scan(db, percorse)
    db.commit()
    assert db.scalar(select(Track).where(Track.audio_hash == "H1")) is not None

    shutil.rmtree(lib)  # disco esterno non montato

    summary = scan(db, percorse)
    db.commit()

    assert db.scalar(select(Track).where(Track.audio_hash == "H1")) is not None, (
        "traccia CANCELLATA da uno scan su radice smontata"
    )
    assert summary.linking["orphans_removed"] == 0
    assert summary.linking["scanned"] == 0, "la fase 2 legge lo stato PRIMA di _reconcile"


def test_file_spostato_in_libreria_riceve_la_traccia_nella_stessa_corsa(
    db, fake_audio, monkeypatch
):
    """Il percorso più battuto: l'Apply sposta un file da inbox a libreria e il
    frontend lancia subito uno scan.

    `_reconcile` fonde la riga e le riscrive `path` e `location='library'` in
    memoria; senza flush la SELECT della fase 2 filtra ancora sulla `location`
    vecchia e la riga è invisibile — il file organizzato resta senza Track fino
    alla scansione successiva, che l'utente non ha motivo di lanciare.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    _due_radici(monkeypatch, lib, inbox)
    sorgente = make("inbox/a.mp3", digest="H1", artist="A", title="A")
    # Registra hash e tag anche per il path di ARRIVO (la fixture li indicizza
    # per path): il file ci arriverà con l'Apply, non deve esistere adesso.
    destinazione = make("lib/a.mp3", digest="H1", artist="A", title="A")
    destinazione.unlink()

    percorse = list(radici(db).values())
    primo = scan(db, percorse)
    db.commit()
    assert primo.linking["created"] == 0  # un file in inbox non è un possesso

    shutil.move(str(sorgente), str(destinazione))  # l'Apply

    summary = scan(db, percorse)
    db.commit()

    assert summary.moved == 1
    assert summary.linking["scanned"] == 1, "la riga fusa è invisibile alla fase 2"
    assert summary.linking["created"] == 1
    riga = db.scalar(select(AudioFile))
    assert riga.location == "library" and riga.track_id is not None
