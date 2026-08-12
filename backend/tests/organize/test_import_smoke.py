"""Il codice Organize è importabile dal namespace app.organize e condivide
Base/engine con Cratory (F2: un solo DB)."""


def test_moduli_organize_importabili():
    from app.organize import models, schemas  # noqa: F401
    from app.organize.core import http_errors  # noqa: F401


def test_base_condiviso():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base

    assert "audio_file" in Base.metadata.tables
    assert "tracks" in Base.metadata.tables
