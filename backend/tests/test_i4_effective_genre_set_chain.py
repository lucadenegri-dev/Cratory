"""I4: il genere EFFETTIVO (tag del file, fallback streaming) deve attraversare
TUTTA la catena di set building, non solo il filtro di ammissione del candidate
engine. Prima della correzione, `candidate_engine.select_candidates` ammetteva
una traccia confrontando `effective_genre(db, t)` ma tutto ciò che stava a valle
(set_skeleton, set_generator, scoring.classify_transition, ai_curation) leggeva
`Track.genre` (il valore streaming), disallineando piano di genere, bonus dei
generi richiesti, similarità e payload AI dal genere che aveva davvero ammesso
la traccia. Vedi .superpowers/sdd/work-a-brief.md.
"""

import pytest
from sqlalchemy import event

from app.models import Track
from app.organize.models import AudioFile, ScanRoot


@pytest.fixture()
def make_owned(db):
    """Factory: crea una Track con un AudioFile primario dai tag dati (stesso
    pattern di test_library_effective_tags.py, duplicato qui per tenere questo
    file autonomo)."""
    root = ScanRoot(path="/tmp/lib")
    db.add(root)
    db.flush()

    def make(*, track_kw=None, file_kw=None) -> Track:
        t = Track(source_type="spotify", **(track_kw or {}))
        db.add(t)
        db.flush()
        f = AudioFile(
            root_id=root.id, track_id=t.id, path=f"/tmp/lib/{t.id}.mp3",
            ext=".mp3", size_bytes=1, hash_method="stream",
            status="present", location="library", **(file_kw or {}),
        )
        db.add(f)
        db.flush()
        t.primary_file_id = f.id
        t.has_local_file = True
        db.commit()
        return t

    return make


# --- 1) Il bonus dei generi richiesti (set_generator._candidate_score) -------
# Test obbligatorio del brief: Track.genre="Electronic", tag file "Progressive
# House", richiesta genres=["Progressive House"] -> la traccia riceve il bonus.
# La verifica di non-vacuità (rosso prima/verde dopo) è documentata nel report.


def test_requested_genre_bonus_absent_without_genre_map(db, make_owned):
    """Comportamento pre-I4 preservato quando nessuno passa la mappa: il bonus
    legge Track.genre streaming, quindi qui NON scatta (entrambe "Electronic")."""
    from app.services.set_generator import _DEFAULT_PROFILE, _candidate_score

    prev = Track(source_type="spotify", bpm=128, camelot_key="8A", energy=70,
                genre="Electronic", duration_seconds=300)
    matching = make_owned(
        track_kw={"title": "M", "artist": "A", "genre": "Electronic",
                 "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                 "duration_seconds": 300},
        file_kw={"genre": "Progressive House"},
    )
    from app.services.set_generator import BeamParams

    req = BeamParams(genres=["Progressive House"])
    s_no_map, _ = _candidate_score(prev, matching, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                   genre_counts={})  # genre_map di default None
    s_with_map, _ = _candidate_score(prev, matching, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                     genre_counts={}, genre_map={matching.id: "Progressive House"})
    assert s_with_map > s_no_map


# --- 2) Il piano di genere/famiglie (set_skeleton.plan_genre_families) ------


# --- 3) classify_transition: retrocompatibilità per i chiamanti fuori dal ----
#        Set Builder (/api/transitions, alternatives, dettaglio traccia)


def test_classify_transition_without_genre_map_keeps_streaming_behavior():
    """Senza `genre_map` (default None) `classify_transition` deve comportarsi
    ESATTAMENTE come prima di I4: legge Track.genre, non un tag file. Protegge
    /api/transitions, alternatives, set_editor — che non passano la mappa."""
    from app.services.scoring import classify_transition

    # BPM/key deboli cosi' non cade nel ramo "technically_safe" (che non guarda
    # affatto il genere) e la classificazione dipende dal cambio di genere.
    prev = Track(source_type="spotify", bpm=128, camelot_key="8A",
                energy=70, genre="Techno", duration_seconds=300)
    cand = Track(source_type="spotify", bpm=150, camelot_key="2B",
                energy=68, genre="Techno", duration_seconds=300)
    cand.id = 999  # id arbitrario: deve essere ignorato senza una mappa

    # Senza mappa: stesso genere streaming ("Techno") su entrambe -> nessun
    # cambio di genere rilevato -> resta un azzardo creativo, non un reset.
    baseline = classify_transition(prev, cand)
    assert baseline.label == "creative_risk"

    # Con una mappa che dice che `cand` è in realtà "Ambient" sul file, la
    # classificazione CAMBIA (reset di genere) — prova che la mappa è l'unica
    # differenza, cioè che senza di essa il comportamento è quello di prima.
    with_map = classify_transition(prev, cand, genre_map={cand.id: "Ambient"})
    assert with_map.label == "good_reset"
    assert baseline.label != with_map.label


# --- 4) candidate_engine: una query in blocco, non una per traccia ----------


# --- 5) ai_curation: il payload mandato all'AI descrive il genere effettivo -


# --- 6) End-to-end: generate_set rispetta il tag file per la copertura ------
#        dei generi richiesti (l'effetto piu' netto secondo il brief)


