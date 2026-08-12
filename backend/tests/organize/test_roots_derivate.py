"""Le radici non sono più gestite dall'utente: si derivano da Settings."""

import pytest
from sqlalchemy import select

from app.organize.models import ScanRoot
from app.organize.services.roots import radici, root_id_per

LIB = "/Users/x/Music/Library"
INBOX = "/Users/x/Music/Downloads"


@pytest.fixture(autouse=True)
def _cartelle(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "library_root", LIB)
    monkeypatch.setattr(settings, "slskd_download_dir", INBOX)


def test_crea_le_due_radici_se_mancano(db):
    esito = radici(db)
    db.flush()

    assert set(esito) == {"library", "inbox"}
    assert esito["library"].path == LIB
    assert esito["inbox"].path == INBOX
    assert db.scalar(select(ScanRoot).where(ScanRoot.path == LIB)) is not None


def test_e_idempotente(db):
    # NB: la tabella scan_root del DB di test contiene già le righe storiche
    # seminate da `_fresh_db` (id 1/2, label NULL, path "/inbox" e "/library" —
    # per soddisfare la FK di altri test). Contiamo solo le righe *gestite* da
    # `radici()` (quelle con una label), non il totale della tabella.
    radici(db)
    db.flush()
    radici(db)
    db.flush()

    assert len(db.scalars(select(ScanRoot).where(ScanRoot.label.isnot(None))).all()) == 2


def test_adotta_una_radice_storica_senza_label(db):
    """Sul DB reale le due righe hanno label NULL: vanno adottate, non duplicate.

    È il caso che su un DB di test fresco non si presenta mai — e proprio per
    questo è quello che va testato."""
    storica = ScanRoot(path=LIB, label=None)
    db.add(storica)
    db.flush()
    id_storico = storica.id

    esito = radici(db)
    db.flush()

    assert esito["library"].id == id_storico
    assert esito["library"].label == "Libreria"
    assert len(db.scalars(select(ScanRoot).where(ScanRoot.path == LIB)).all()) == 1


def test_riallinea_una_radice_esistente_se_la_cartella_cambia(db, monkeypatch):
    """Cambiare LIBRARY_ROOT in .env non deve creare una terza radice orfana."""
    from app.core.config import settings

    prima = radici(db)["library"]
    db.flush()
    id_prima = prima.id

    monkeypatch.setattr(settings, "library_root", "/Users/x/Music/Library2")
    dopo = radici(db)["library"]
    db.flush()

    assert dopo.id == id_prima          # stessa riga, non una nuova
    assert dopo.path == "/Users/x/Music/Library2"
    assert len(db.scalars(select(ScanRoot).where(ScanRoot.label.isnot(None))).all()) == 2


def test_salta_la_radice_non_configurata(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "slskd_download_dir", "")
    esito = radici(db)
    db.flush()

    assert set(esito) == {"library"}


def test_root_id_per_location(db):
    esito = radici(db)
    db.flush()

    assert root_id_per(db, "library") == esito["library"].id
    assert root_id_per(db, "inbox") == esito["inbox"].id
