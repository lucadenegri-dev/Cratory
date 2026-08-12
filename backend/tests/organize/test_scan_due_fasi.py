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
    assert summary.linking is not None and summary.linking.created == 1


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
    assert secondo.linking.created == 0
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
    assert summary.linking.energy_computed == 3


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
    # `in` su un BaseModel itera le coppie (chiave, valore) e non trova mai una
    # stringa: dopo la tipizzazione di `linking` un `not in` sarebbe sempre vero,
    # cioè vacuo. Il campo esiste sempre, quindi si asserisce sul valore.
    assert summary.linking.energy_computed is None


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
    # Il duplicato lo trova il giro d'ARCHIVIO (il digest era già stato visto
    # dalla libreria), non quello di libreria: finché i due contatori erano
    # sommati sotto `duplicates` questa distinzione non si poteva fare.
    assert summary.linking.archive_duplicates == 1
    assert summary.linking.duplicates == 0


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
    assert summary.linking.archived == 1
    assert summary.linking.orphans_removed == 0


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
    assert summary.linking.orphans_removed == 0
    assert summary.linking.scanned == 0, "la fase 2 legge lo stato PRIMA di _reconcile"


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
    assert primo.linking.created == 0  # un file in inbox non è un possesso

    shutil.move(str(sorgente), str(destinazione))  # l'Apply

    summary = scan(db, percorse)
    db.commit()

    assert summary.moved == 1
    assert summary.linking.scanned == 1, "la riga fusa è invisibile alla fase 2"
    assert summary.linking.created == 1
    riga = db.scalar(select(AudioFile))
    assert riga.location == "library" and riga.track_id is not None


def test_scan_del_solo_inbox_non_tocca_le_tracce(db, fake_audio, monkeypatch):
    """`POST /api/organize/scan {"locations":["inbox"]}` — un clic dal filtro
    Inbox — cammina solo l'inbox: le righe di libreria non vengono riconciliate
    e restano `present`, quindi `scanned` non è zero e l'anti-unmount non
    scatta nemmeno con la flush a posto. La fase di aggancio deve girare solo
    se lo scan ha davvero camminato la radice della libreria.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    _due_radici(monkeypatch, lib, inbox)
    make("lib/a.mp3", digest="H1", artist="A", title="A")
    make("inbox/b.mp3", digest="H2", artist="B", title="B")

    per_loc = radici(db)
    scan(db, list(per_loc.values()))
    db.commit()
    assert len(db.scalars(select(Track)).all()) == 1

    shutil.rmtree(lib)  # libreria non montata

    summary = scan(db, [per_loc["inbox"]])
    db.commit()

    tracce = db.scalars(select(Track)).all()
    assert len(tracce) == 1 and tracce[0].audio_hash == "H1", (
        "uno scan del solo inbox ha creato o cancellato tracce"
    )
    assert summary.linking is None, "fase di aggancio eseguita senza camminare la libreria"


def test_il_progresso_non_torna_indietro(db, fake_audio, monkeypatch):
    """Due `total` diversi sulla stessa callback facevano scendere la percentuale
    al passaggio fra le fasi: la barra mostrava 100% e poi ripartiva da 0."""
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    for i in range(4):
        make(f"lib/A - T{i}.mp3", digest=f"H{i}", artist="A", title=f"T{i}")

    frazioni: list[float] = []

    def on_progress(processed: int, total: int, phase: str) -> None:
        if total:
            frazioni.append(processed / total)

    scan(db, [radici(db)["library"]], on_progress=on_progress)

    assert frazioni == sorted(frazioni), f"progresso non monotono: {frazioni}"
