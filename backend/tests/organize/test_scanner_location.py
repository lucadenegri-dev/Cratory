"""Lo scanner deve derivare `location`, non lasciarla al default del modello.

Senza questo, ogni file scansionato dopo il backfill nasce con location="inbox"
anche se sta in LIBRARY_ROOT: il campo si degrada in silenzio a partire dal
primo scan.
"""

import pytest
from sqlalchemy import select

from app.organize.models import AudioFile, ScanRoot
from app.organize.services import roots as roots_svc
from app.organize.services import scanner


@pytest.fixture()
def radici(tmp_path, monkeypatch):
    """Due cartelle vere, configurate come le radici di Settings."""
    library = tmp_path / "Library"
    inbox = tmp_path / "Downloads"
    library.mkdir()
    inbox.mkdir()
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", str(library))
    monkeypatch.setattr(settings, "slskd_download_dir", str(inbox))
    return library, inbox


def _mp3(dirpath, nome: str):
    p = dirpath / nome
    p.write_bytes(b"ID3" + b"\x00" * 200)
    return p


def test_file_in_library_nasce_con_location_library(db, radici, monkeypatch):
    library, _ = radici
    _mp3(library, "a.mp3")

    root = ScanRoot(path=str(library))
    db.add(root)
    db.commit()

    scanner.scan(db, [root])
    db.commit()

    f = db.scalar(select(AudioFile).where(AudioFile.path.like(f"{library}%")))
    assert f is not None
    assert f.location == "library"


def test_file_in_inbox_nasce_con_location_inbox(db, radici):
    _, inbox = radici
    _mp3(inbox, "b.mp3")

    root = ScanRoot(path=str(inbox))
    db.add(root)
    db.commit()

    scanner.scan(db, [root])
    db.commit()

    f = db.scalar(select(AudioFile).where(AudioFile.path.like(f"{inbox}%")))
    assert f is not None
    assert f.location == "inbox"


def test_inbox_annidata_nella_libreria_non_duplica_ne_marca_missing(db, tmp_path, monkeypatch):
    """La root percorsa e la root derivata sono due nozioni distinte.

    Con SLSKD_DOWNLOAD_DIR annidata dentro LIBRARY_ROOT (config del tutto
    legittima: `~/Music` e `~/Music/Downloads`) ogni file dell'inbox viene
    percorso due volte — una camminando la libreria, una camminando l'inbox — e
    `deriva_location` dà in entrambi i casi "library". Se la ricerca del
    "già indicizzato?" e la riconciliazione restano agganciate alla root
    percorsa, il primo scan muore sulla UNIQUE (root_id, path) e i successivi
    marcano `missing` righe che stanno benissimo dove sono.
    """
    from app.core.config import settings

    library = tmp_path / "Music"
    inbox = library / "Downloads"
    inbox.mkdir(parents=True)
    monkeypatch.setattr(settings, "library_root", str(library))
    monkeypatch.setattr(settings, "slskd_download_dir", str(inbox))
    _mp3(inbox, "a.mp3")

    percorse = list(roots_svc.radici(db).values())
    db.commit()

    primo = scanner.scan(db, percorse)
    assert primo.found == 1          # un file solo, per quante volte lo si percorra
    assert primo.inserted == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1

    secondo = scanner.scan(db, percorse)
    assert secondo.inserted == 0 and secondo.missing == 0
    assert secondo.updated == 1
    db.expire_all()
    righe = db.scalars(select(AudioFile)).all()
    assert len(righe) == 1
    assert righe[0].status == "present"


def test_file_che_passa_da_inbox_a_libreria_cambia_root_id(db, radici):
    """È ciò che fa un Apply: il file esce dall'inbox ed entra in libreria.

    Lo scan successivo deve riconoscere lo spostamento (stesso content_hash) e
    riallineare `location` E `root_id`, non lasciare la riga agganciata alla
    radice sbagliata.
    """
    library, inbox = radici
    _mp3(inbox, "a.mp3")

    percorse = list(roots_svc.radici(db).values())
    id_per = {loc: r.id for loc, r in roots_svc.radici(db).items()}
    db.commit()

    scanner.scan(db, percorse)
    prima = db.scalar(select(AudioFile))
    id_riga = prima.id
    assert prima.location == "inbox" and prima.root_id == id_per["inbox"]

    (inbox / "a.mp3").rename(library / "a.mp3")

    summary = scanner.scan(db, percorse)
    assert summary.moved == 1 and summary.missing == 0 and summary.inserted == 0
    db.expire_all()
    righe = db.scalars(select(AudioFile)).all()
    assert len(righe) == 1
    assert righe[0].id == id_riga            # stessa riga, non una nuova
    assert righe[0].path == str(library / "a.mp3")
    assert righe[0].location == "library"
    assert righe[0].root_id == id_per["library"]
