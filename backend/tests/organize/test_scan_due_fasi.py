"""Uno scan solo produce l'indice dei file E le tracce."""

import os
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


def test_file_spostato_dentro_la_libreria_tiene_la_sua_traccia(
    db, fake_audio, monkeypatch
):
    """L'altro percorso dell'Apply: un file GIÀ in libreria, con la sua Track,
    viene spostato/rinominato dal template e il frontend lancia lo scan.

    Uno spostamento conserva mtime e dimensione, quindi la fase 2 prende la via
    veloce degli invariati: vede il path nuovo ma deve anche riscriverlo sulla
    Track. Se `Track.local_path` resta quello vecchio, `riconcilia_possessi` la
    trova "persa" e — non essendo in nessuna playlist — la CANCELLA, con BPM e
    key; la riga del file resta senza traccia fino allo scan successivo, che ne
    conia una nuova e vuota.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    inbox.mkdir()
    _due_radici(monkeypatch, lib, inbox)
    sorgente = make("lib/a.mp3", digest="H1", artist="A", title="A")
    destinazione = make("lib/A/A - A.mp3", digest="H1", artist="A", title="A")
    destinazione.unlink()

    percorse = list(radici(db).values())
    scan(db, percorse)
    db.commit()
    traccia = db.scalar(select(Track).where(Track.audio_hash == "H1"))
    traccia.bpm, traccia.camelot_key = 128.0, "8A"
    db.commit()
    id_prima = traccia.id

    shutil.move(str(sorgente), str(destinazione))  # l'Apply

    summary = scan(db, percorse)
    db.commit()
    db.expire_all()

    assert summary.moved == 1
    assert summary.linking.orphans_removed == 0, "la Track del file spostato è stata cancellata"
    assert summary.linking.lost == 0
    assert summary.linking.relinked == 1
    traccia = db.get(Track, id_prima)
    assert traccia is not None
    assert (traccia.bpm, traccia.camelot_key) == (128.0, "8A")
    assert traccia.has_local_file and traccia.local_path == str(destinazione.resolve())
    assert db.scalar(select(AudioFile)).track_id == id_prima


def test_traccia_scollegata_col_file_ancora_in_libreria_torna_posseduta(
    db, fake_audio, monkeypatch
):
    """Lo stato che il bug dello spostamento ha lasciato sulle tracce in
    playlist (in produzione, «Presence» di Basic Channel): la riconciliazione
    le ha sganciate — `has_local_file` falso, niente `local_path` — ma la riga
    del file in libreria punta ancora alla Track, e mtime e dimensione sono
    quelli registrati. La via veloce degli invariati non deve prenderla: una
    traccia non posseduta va ripossessata dal flusso completo, con i suoi dati.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    inbox.mkdir()
    _due_radici(monkeypatch, lib, inbox)
    a = make("lib/a.mp3", digest="H1", artist="A", title="A")
    percorse = list(radici(db).values())
    scan(db, percorse)
    db.commit()
    traccia = db.scalar(select(Track).where(Track.audio_hash == "H1"))
    traccia.bpm, traccia.camelot_key = 124.98, "3A"
    # Cosa fa `riconcilia_possessi` a una traccia persa ma in playlist.
    traccia.has_local_file = False
    traccia.local_path = traccia.local_format = traccia.local_bitrate = None
    traccia.primary_file_id = None
    db.commit()
    id_prima = traccia.id

    scan(db, percorse)
    db.commit()
    db.expire_all()

    traccia = db.get(Track, id_prima)
    assert traccia.has_local_file
    assert traccia.local_path == str(a.resolve())
    assert (traccia.bpm, traccia.camelot_key) == (124.98, "3A")
    riga = db.scalar(select(AudioFile))
    assert riga.track_id == id_prima and traccia.primary_file_id == riga.id


def test_traccia_posseduta_senza_link_al_file_lo_ritrova(db, fake_audio, monkeypatch):
    """Una Track posseduta col `local_path` giusto ma senza link alla sua riga
    (`primary_file_id` e `AudioFile.track_id` vuoti — in produzione «Power to
    the People» di Pardon Moi): la via veloce la trova per path e la conta
    invariata, ma senza `aggiorna_primary` il link non si ricuce mai, e le
    funzioni di Organize che passano da lì non vedono la traccia.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    inbox.mkdir()
    _due_radici(monkeypatch, lib, inbox)
    make("lib/a.mp3", digest="H1", artist="A", title="A")
    percorse = list(radici(db).values())
    scan(db, percorse)
    db.commit()
    traccia = db.scalar(select(Track).where(Track.audio_hash == "H1"))
    riga = db.scalar(select(AudioFile))
    traccia.primary_file_id = None
    riga.track_id = None
    db.commit()

    summary = scan(db, percorse)
    db.commit()
    db.expire_all()

    assert summary.linking.unchanged == 1
    assert db.get(Track, traccia.id).primary_file_id == riga.id
    assert db.get(AudioFile, riga.id).track_id == traccia.id


def test_due_copie_vive_della_stessa_traccia_non_si_rubano_il_path(
    db, fake_audio, monkeypatch
):
    """Il rovescio del test sopra: la riscrittura di `local_path` sulla via
    veloce vale solo se il path vecchio non esiste più. Due righe possono
    portare lo stesso `track_id` (un file tornato dalla quarantena con l'undo
    dopo che la traccia si era agganciata a una copia): con entrambi i file
    vivi e la stessa firma, la Track resta dov'era invece di saltare
    sull'ultima riga visitata a ogni scan.
    """
    make, root = fake_audio
    lib, inbox = root / "lib", root / "inbox"
    inbox.mkdir()
    _due_radici(monkeypatch, lib, inbox)
    a = make("lib/a.mp3", digest="H1", artist="A", title="A")
    percorse = list(radici(db).values())
    scan(db, percorse)
    db.commit()
    traccia = db.scalar(select(Track).where(Track.audio_hash == "H1"))
    path_a = traccia.local_path

    b = make("lib/b.mp3", digest="H1", artist="A", title="A")
    st = a.stat()
    os.utime(b, ns=(st.st_atime_ns, st.st_mtime_ns))  # stessa firma di a
    scan(db, percorse)  # b entra nell'indice come duplicato, senza traccia
    db.commit()
    riga_b = db.scalar(select(AudioFile).where(AudioFile.path == str(b.resolve())))
    riga_b.track_id = traccia.id  # il link rimasto alla copia
    db.commit()

    summary = scan(db, percorse)
    db.commit()
    db.expire_all()

    assert db.get(Track, traccia.id).local_path == path_a
    assert summary.linking.relinked == 0


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

