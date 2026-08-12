"""Invarianti della libreria che il modello Track 1─N AudioFile dà per scontati."""

from sqlalchemy import func, select

from app.models import Track


def _duplicati_per_path(db) -> list:
    """Il rilevatore. Tenuto separato dai test perché entrambi lo usano: uno
    verifica che sappia vedere il caso cattivo, l'altro che il codice non lo crei."""
    return db.execute(
        select(Track.local_path, func.count())
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).all()


def test_il_rilevatore_vede_un_duplicato_quando_c_e(db):
    """Prima di fidarsi del rilevatore, verificare che sappia dire di no.

    La versione precedente di questo file seminava due path DIVERSI e poi
    asseriva l'assenza di duplicati: non poteva fallire, e infatti non ha visto
    la regressione di fine F3b."""
    db.add_all([
        Track(source_type="spotify", has_local_file=True, local_path="/lib/a.flac"),
        Track(source_type="local_files", has_local_file=True, local_path="/lib/a.flac"),
    ])
    db.commit()

    doppi = _duplicati_per_path(db)
    assert len(doppi) == 1
    assert doppi[0][0] == "/lib/a.flac"


def test_l_indicizzazione_non_crea_un_duplicato_per_path(db, fake_audio, collega_da_disco):
    """L'invariante vero: non che i duplicati si vedano, ma che il codice non
    li produca. Stesse condizioni della regressione di fine F3b — traccia
    posseduta, file con hash diverso, nessun ISRC nei tag."""
    make, root = fake_audio
    p = make("Trance/R/R - Aqua Viva.mp3", digest="H_NUOVO", artist="R", title="Aqua Viva")
    db.add(Track(source_type="spotify", spotify_id="s1", artist="R", title="Aqua Viva",
                 has_local_file=True, local_path=str(p.resolve()), audio_hash="H_VECCHIO"))
    db.commit()

    collega_da_disco(root)

    assert _duplicati_per_path(db) == []
