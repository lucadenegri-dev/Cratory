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
from app.schemas import SetGenerationRequest


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


def test_requested_genre_bonus_uses_effective_genre_not_streaming(db, make_owned):
    from app.services.candidate_engine import select_candidates
    from app.services.set_generator import _DEFAULT_PROFILE, _REQUESTED_GENRE_BONUS, _candidate_score

    prev = Track(source_type="spotify", bpm=128, camelot_key="8A", energy=70,
                genre="Electronic", duration_seconds=300)
    # Streaming identico ("Electronic") per entrambe: solo il tag file le distingue.
    matching = make_owned(
        track_kw={"title": "M", "artist": "A", "genre": "Electronic",
                 "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                 "duration_seconds": 300},
        file_kw={"genre": "Progressive House"},
    )
    other = make_owned(
        track_kw={"title": "O", "artist": "B", "genre": "Electronic",
                 "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                 "duration_seconds": 300},
        file_kw={"genre": "Witch House"},
    )
    req = SetGenerationRequest(genres=["Progressive House"])
    # select_candidates risolve la mappa in blocco (stessa che ammette al pool):
    # qui ci interessa solo la mappa, non il pool filtrato.
    _, genre_map = select_candidates(db, req)
    assert genre_map[matching.id] == "Progressive House"
    assert genre_map[other.id] == "Witch House"

    s_matching, _ = _candidate_score(prev, matching, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                     genre_counts={}, genre_map=genre_map)
    s_other, _ = _candidate_score(prev, other, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                  genre_counts={}, genre_map=genre_map)
    # Le due candidate sono identiche su tutto il resto (bpm/key/energia/durata,
    # e Track.genre uguale): l'unica differenza possibile è il bonus di copertura
    # del genere richiesto, che scatta SOLO per chi ha il tag file richiesto.
    assert s_matching - s_other == pytest.approx(_REQUESTED_GENRE_BONUS)


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
    req = SetGenerationRequest(genres=["Progressive House"])
    s_no_map, _ = _candidate_score(prev, matching, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                   genre_counts={})  # genre_map di default None
    s_with_map, _ = _candidate_score(prev, matching, 128.0, req, {}, _DEFAULT_PROFILE, 0.5,
                                     genre_counts={}, genre_map={matching.id: "Progressive House"})
    assert s_with_map > s_no_map


# --- 2) Il piano di genere/famiglie (set_skeleton.plan_genre_families) ------


def test_plan_genre_families_uses_effective_genre(db, make_owned):
    """Tutte le tracce hanno lo stesso Track.genre="Electronic" (termine
    ombrello, nessuna famiglia nota): senza genere effettivo il piano degenera
    a None anche se sul file le famiglie sono ben distinte. DEVE fallire se
    `plan_genre_families` torna a leggere `t.genre`."""
    from app.services.set_skeleton import plan_genre_families

    pool = []
    # 5 techno (63%), 2 house (25%, sopra soglia 15%): piano valido SOLO se si
    # legge il tag file, perché lo streaming è "Electronic" per tutte.
    for i in range(5):
        pool.append(make_owned(
            track_kw={"title": f"T{i}", "artist": f"A{i}", "genre": "Electronic",
                     "bpm": 128.0, "energy": 80, "duration_seconds": 300},
            file_kw={"genre": "Techno"},
        ))
    for i in range(2):
        pool.append(make_owned(
            track_kw={"title": f"H{i}", "artist": f"B{i}", "genre": "Electronic",
                     "bpm": 124.0, "energy": 40, "duration_seconds": 300},
            file_kw={"genre": "House"},
        ))

    genre_map = {t.id: t.files[0].genre for t in pool}

    assert plan_genre_families(pool) is None  # comportamento pre-I4 (streaming uniforme)
    plan = plan_genre_families(pool, genre_map)
    assert plan is not None
    assert plan.principal == "techno"
    assert plan.calm == "house"


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


def test_select_candidates_resolves_genre_in_one_query_not_per_track(db, make_owned):
    """Conta le query SQL eseguite durante `select_candidates`: deve restare
    costante (poche query fisse) al crescere del pool, non proporzionale al
    numero di tracce (N+1 di prima, `effective_genre(db, t)` in un ciclo)."""
    from app.services.candidate_engine import select_candidates

    def _seed(n: int, start: int) -> None:
        for i in range(start, start + n):
            make_owned(
                track_kw={"title": f"T{i}", "artist": f"A{i}", "genre": "Electronic",
                         "bpm": 128.0, "camelot_key": "8A", "duration_seconds": 300},
                file_kw={"genre": "Techno"},
            )

    engine = db.get_bind()
    queries: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        _seed(5, 0)
        queries.clear()
        select_candidates(db, SetGenerationRequest())
        small_count = len(queries)

        _seed(60, 1000)
        queries.clear()
        select_candidates(db, SetGenerationRequest())
        big_count = len(queries)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # Stesso numero di query indipendentemente dal numero di tracce nel pool:
    # se `effective_genre` fosse ancora chiamata per traccia, big_count
    # crescerebbe con la dimensione del pool (N+1).
    assert small_count == big_count
    assert small_count <= 6  # poche query fisse (tracks + eager load + genere in blocco)


# --- 5) ai_curation: il payload mandato all'AI descrive il genere effettivo -


def test_candidate_payload_uses_effective_genre():
    from app.models import Track as TrackModel
    from app.services.ai_curation import _candidate_payload

    t = TrackModel(source_type="spotify", title="T", artist="A", genre="Electronic",
                   bpm=128.0, camelot_key="8A", duration_seconds=300)
    t.id = 1
    assert _candidate_payload(t)["genre"] == "Electronic"  # nessuna mappa: streaming
    assert _candidate_payload(t, {1: "Progressive House"})["genre"] == "Progressive House"


# --- 6) End-to-end: generate_set rispetta il tag file per la copertura ------
#        dei generi richiesti (l'effetto piu' netto secondo il brief)


def test_generate_set_surfaces_requested_genre_from_file_tag_not_streaming(db, make_owned):
    """Libreria con Track.genre uniforme "Electronic" (come se venisse tutta da
    streaming) ma tag file differenziati: il set richiesto con generi ESPLICITI
    presi dal tag file deve comunque contenerli tutti (bonus di copertura). Se
    la catena tornasse a leggere Track.genre, "breakbeat"/"dub" non
    comparirebbero mai (nessuna traccia li ha in streaming)."""
    from app.services.set_generator import generate_set

    i = 0
    for _ in range(24):
        make_owned(
            track_kw={"title": f"T{i}", "artist": f"Art{i}", "genre": "Electronic",
                     "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                     "duration_seconds": 200},
            file_kw={"genre": "Techno"},
        )
        i += 1
    for _ in range(4):
        make_owned(
            track_kw={"title": f"T{i}", "artist": f"Art{i}", "genre": "Electronic",
                     "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                     "duration_seconds": 200},
            file_kw={"genre": "Breakbeat"},
        )
        i += 1
    for _ in range(4):
        make_owned(
            track_kw={"title": f"T{i}", "artist": f"Art{i}", "genre": "Electronic",
                     "bpm": 128.0, "camelot_key": "8A", "energy": 70,
                     "duration_seconds": 200},
            file_kw={"genre": "Dub"},
        )
        i += 1

    sl = generate_set(db, SetGenerationRequest(
        genres=["dub", "breakbeat", "techno"], start_bpm=128, end_bpm=128,
        target_duration_minutes=30, max_tracks_per_artist=5))
    file_genres = {(st.track.files[0].genre or "").lower() for st in sl.tracks}
    assert {"dub", "breakbeat", "techno"} <= file_genres
    # Il difetto I4: se si leggesse Track.genre, TUTTE le tracce risulterebbero
    # "electronic" e la copertura sarebbe impossibile da verificare così.
    streaming_genres = {(st.track.genre or "").lower() for st in sl.tracks}
    assert streaming_genres == {"electronic"}
