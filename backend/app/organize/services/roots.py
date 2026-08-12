"""Le due radici canoniche, derivate da Settings.

`scan_root` non è più un'entità gestita dall'utente: da F3b esistono esattamente
due cartelle, `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`, e la tabella le rispecchia.

La tabella sopravvive come **schema morto**: `audio_file.root_id` è NOT NULL con
una FK viva e SQLite non può droppare la colonna (è dentro `uq_audio_root_path`),
quindi ogni file nuovo deve comunque puntare a una riga esistente. Qui c'è
l'unico posto che le scrive. Vedi la spiegazione in testa al piano F3b.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.organize.models import ScanRoot

# label -> lettura della cartella dalle Settings. La label identifica la riga
# nel tempo: cambiare la cartella in .env riallinea la riga, non ne crea una nuova.
_LABEL = {"library": "Libreria", "inbox": "Inbox"}


def _cartella(location: str) -> str:
    return (runtime_settings.library_root() if location == "library"
            else runtime_settings.slskd_download_dir())


def radici(db: Session) -> dict[str, ScanRoot]:
    """Le radici esistenti e allineate alle cartelle configurate.

    Idempotente. Una cartella non configurata (stringa vuota) non produce riga:
    quella metà dello scan è semplicemente inattiva, come già fa Cratory con
    LIBRARY_ROOT vuoto. Non fa commit.
    """
    esito: dict[str, ScanRoot] = {}
    for location, label in _LABEL.items():
        cartella = _cartella(location)
        if not cartella:
            continue
        riga = db.scalar(select(ScanRoot).where(ScanRoot.label == label))
        if riga is None:
            # ADOZIONE. Sul DB reale le due righe storiche hanno label NULL (le
            # sorgenti le aveva create l'utente, senza etichetta): cercarle solo
            # per label ne creerebbe due nuove e lascerebbe i 1778 file
            # esistenti agganciati a righe che nessuno mantiene più. Si adotta
            # la riga che punta già alla cartella giusta, stampandole la label —
            # da lì in avanti è la label a identificarla, così un cambio di
            # cartella in .env riallinea invece di duplicare.
            riga = db.scalar(select(ScanRoot).where(ScanRoot.path == cartella,
                                                    ScanRoot.label.is_(None)))
        if riga is None:
            riga = ScanRoot(path=cartella, label=label)
            db.add(riga)
        else:
            riga.label = label
            riga.path = cartella
        # target_root resta NULL: la destinazione ora la dà planning.target_root().
        riga.target_root = None
        esito[location] = riga
    db.flush()
    return esito


def root_id_per(db: Session, location: str) -> int:
    """L'id da scrivere su `audio_file.root_id` per un file di quella collocazione."""
    riga = radici(db).get(location)
    if riga is None:
        raise ValueError(f"cartella non configurata per location={location!r}")
    return riga.id
