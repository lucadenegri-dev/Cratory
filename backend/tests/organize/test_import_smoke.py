"""Il codice Organize deve essere importabile dal namespace app.organize e
mantenere un proprio Base/engine distinto da quello di Cratory (F1: due DB)."""


def test_moduli_organize_importabili():
    from app.organize import db, models, schemas  # noqa: F401
    from app.organize.core import config  # noqa: F401


def test_base_organize_distinto_da_quello_cratory():
    from app.db import Base as BaseCratory
    from app.organize.db import Base as BaseOrganize

    assert BaseOrganize is not BaseCratory


def test_audio_file_registrato_solo_sul_base_organize():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base as BaseCratory
    from app.organize.db import Base as BaseOrganize

    assert "audio_file" in BaseOrganize.metadata.tables
    assert "audio_file" not in BaseCratory.metadata.tables
    assert "tracks" in BaseCratory.metadata.tables
