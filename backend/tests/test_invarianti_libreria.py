"""Invarianti della libreria che il modello Track 1─N AudioFile dà per scontati."""

from sqlalchemy import func, select

from app.models import Track


def test_nessuna_traccia_condivide_il_local_path(db):
    """Due Track sullo stesso file renderebbero ambiguo audio_file.track_id,
    che è una FK singola. Vedi la fusione in app/tools/merge_duplicate_tracks."""
    db.add_all([
        Track(source_type="manual", has_local_file=True, local_path="/lib/a.flac"),
        Track(source_type="manual", has_local_file=True, local_path="/lib/b.flac"),
    ])
    db.commit()

    doppi = db.execute(
        select(Track.local_path, func.count())
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).all()
    assert doppi == []
