"""Lo scanner deve derivare `location`, non lasciarla al default del modello.

Senza questo, ogni file scansionato dopo il backfill nasce con location="inbox"
anche se sta in LIBRARY_ROOT: il campo si degrada in silenzio a partire dal
primo scan.
"""

import os

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


def test_rename_in_libreria_non_si_fonde_con_una_copia_gemella_in_inbox(db, radici):
    """La riconciliazione accoppia per solo content_hash: preferire la stessa radice.

    Trovare copie byte-identiche fra inbox e libreria è uno degli scopi
    dell'applicazione, quindi due file con lo stesso hash sono la norma. Qui un
    file viene rinominato DENTRO la libreria mentre in inbox ne arriva una copia
    identica: se vince il primo insert in ordine di walk (inbox percorsa per
    prima), la riga di libreria — con i suoi id, first_seen_at, track_id e figli
    Issue/DupMember/PlanOp/UndoJournal — finisce puntata sul file dell'altra
    cartella.
    """
    library, inbox = radici
    _mp3(library, "a.mp3")

    per_loc = roots_svc.radici(db)
    id_per = {loc: r.id for loc, r in per_loc.items()}
    # Inbox per prima: l'ordine di walk non deve decidere l'abbinamento.
    percorse = [per_loc["inbox"], per_loc["library"]]
    db.commit()

    scanner.scan(db, percorse)
    id_riga = db.scalar(select(AudioFile)).id

    (library / "a.mp3").rename(library / "b.mp3")
    _mp3(inbox, "gemella.mp3")          # stessi byte, quindi stesso content_hash

    summary = scanner.scan(db, percorse)
    assert summary.moved == 1 and summary.missing == 0 and summary.inserted == 1
    db.expire_all()
    per_path = {r.path: r for r in db.scalars(select(AudioFile)).all()}
    assert set(per_path) == {str(library / "b.mp3"), str(inbox / "gemella.mp3")}
    rinominato = per_path[str(library / "b.mp3")]
    assert rinominato.id == id_riga     # la riga storica segue il rename, non la gemella
    assert rinominato.location == "library" and rinominato.root_id == id_per["library"]
    gemella = per_path[str(inbox / "gemella.mp3")]
    assert gemella.id != id_riga        # la copia in inbox è una riga nuova
    assert gemella.location == "inbox" and gemella.root_id == id_per["inbox"]


def test_hash_conteso_da_piu_righe_non_fonde_nulla(db, radici):
    """Spostare una cartella che contiene una coppia di duplicati.

    Due righe sparite e due insert nuovi condividono lo stesso hash: nessun
    abbinamento è più informato dell'altro. Meglio due missing onesti (le righe
    restano visibili e riconciliabili a mano) che una fusione a caso che
    ripunta i figli di una riga sul file sbagliato e lascia l'altra missing per
    sempre.
    """
    library, _ = radici
    vecchia = library / "vecchia"
    vecchia.mkdir()
    _mp3(vecchia, "a.mp3")
    _mp3(vecchia, "copia.mp3")          # byte-identico: stesso content_hash

    percorse = list(roots_svc.radici(db).values())
    db.commit()

    primo = scanner.scan(db, percorse)
    assert primo.inserted == 2

    vecchia.rename(library / "nuova")

    summary = scanner.scan(db, percorse)
    assert summary.moved == 0
    assert summary.missing == 2 and summary.inserted == 2
    db.expire_all()
    righe = db.scalars(select(AudioFile)).all()
    assert len(righe) == 4
    assert {r.status for r in righe if "vecchia" in r.path} == {"missing"}
    assert {r.status for r in righe if "nuova" in r.path} == {"present"}


def test_riga_di_libreria_sparita_con_gemella_in_inbox_viene_fusa(db, radici):
    """Comportamento accettato del caso 1:1 che attraversa il confine.

    Un file sparisce dalla libreria mentre in inbox ne compare uno
    byte-identico: al livello del content_hash è indistinguibile dall'undo di
    un Apply (che sposta davvero library→inbox), quindi la fusione resta — le
    due guardie la limitano al caso 1:1, dove non c'è alternativa più
    informata. Se la coincidenza non fosse uno spostamento, la riga segue
    comunque il file gemello: è il prezzo noto della chiave larga.
    """
    library, inbox = radici
    _mp3(library, "a.mp3")

    per_loc = roots_svc.radici(db)
    id_per = {loc: r.id for loc, r in per_loc.items()}
    percorse = list(per_loc.values())
    db.commit()

    scanner.scan(db, percorse)
    id_riga = db.scalar(select(AudioFile)).id

    (library / "a.mp3").unlink()
    _mp3(inbox, "gemella.mp3")

    summary = scanner.scan(db, percorse)
    assert summary.moved == 1 and summary.missing == 0 and summary.inserted == 0
    db.expire_all()
    righe = db.scalars(select(AudioFile)).all()
    assert len(righe) == 1
    assert righe[0].id == id_riga
    assert righe[0].path == str(inbox / "gemella.mp3")
    assert righe[0].location == "inbox" and righe[0].root_id == id_per["inbox"]


def test_inbox_symlinkata_dentro_la_libreria_non_duplica_il_file(db, tmp_path, monkeypatch):
    """Due root che raggiungono lo stesso albero per strade diverse.

    Con SLSKD_DOWNLOAD_DIR symlinkata dentro LIBRARY_ROOT, lo stesso file
    fisico viene percorso due volte con due stringhe di path diverse: la dedup
    per stringa grezza non lo vede e l'indice si ritrova due righe per un solo
    file (che duplicate/Apply tratteranno come due file distinti).
    """
    from app.core.config import settings

    library = tmp_path / "Music"
    reale = library / "Downloads"
    reale.mkdir(parents=True)
    link = tmp_path / "inbox-link"
    os.symlink(reale, link)
    monkeypatch.setattr(settings, "library_root", str(library))
    monkeypatch.setattr(settings, "slskd_download_dir", str(link))
    _mp3(reale, "a.mp3")

    percorse = list(roots_svc.radici(db).values())
    db.commit()

    summary = scanner.scan(db, percorse)
    assert summary.found == 1 and summary.inserted == 1
    righe = db.scalars(select(AudioFile)).all()
    assert len(righe) == 1
    assert righe[0].path == str(reale / "a.mp3")


def test_cartella_non_configurata_fallisce_prima_di_scrivere(db, tmp_path, monkeypatch):
    """Fail-fast: la configurazione incompleta si scopre prima del primo insert.

    Con la verifica dentro il loop, i file già visitati sono ancora pendenti
    nella Session quando lo scan muore: nessun commit li salva, ma la Session
    resta sporca in mano al chiamante.
    """
    from app.core.config import settings

    library = tmp_path / "Library"
    fuori = tmp_path / "Altrove"
    library.mkdir()
    fuori.mkdir()
    monkeypatch.setattr(settings, "library_root", str(library))
    monkeypatch.setattr(settings, "slskd_download_dir", "")   # inbox non configurata
    _mp3(library, "a.mp3")
    _mp3(fuori, "b.mp3")

    percorse = list(roots_svc.radici(db).values())            # solo la libreria
    esterna = ScanRoot(path=str(fuori))
    db.add(esterna)
    db.flush()

    with pytest.raises(ValueError):
        scanner.scan(db, percorse + [esterna])

    assert [o for o in db.new if isinstance(o, AudioFile)] == []
