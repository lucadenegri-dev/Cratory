"""Qualità dei testi del set e della classificazione transizioni (PR5):
classificazione onesta, spiegazione utile, warning aggregati, dedup, export accurato.
"""

from app.models import Track
from app.schemas import SetGenerationRequest


def mk(bpm=None, key=None, duration=300, energy=None, genre=None, artist=None, title=None):
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre, artist=artist, title=title)


# --- Fix 5) "tecnicamente sicura" richiede anche l'armonia ------------------

def test_high_score_weak_key_is_not_safe():
    from app.services.scoring import classify_transition
    # BPM perfetto (+1) ma key debole (7B->9B): NON è tecnicamente sicura
    c = classify_transition(mk(bpm=138, key="7B", energy=70, genre="techno"),
                            mk(bpm=139, key="9B", energy=70, genre="techno"))
    assert c.label != "technically_safe"
    assert "tonalità" in c.reason.lower() or "chiave" in c.reason.lower()


def test_high_score_compatible_key_stays_safe():
    from app.services.scoring import classify_transition
    # 8A->9A adiacente (compatibile) + BPM +1: resta sicura
    c = classify_transition(mk(bpm=128, key="8A"), mk(bpm=129, key="9A"))
    assert c.label == "technically_safe"


# --- Fix 1) global_explanation utile, senza gergo ---------------------------

def _scored(tracks):
    from app.services.scoring import score_transition
    out = [(tracks[0], None)]
    for i in range(1, len(tracks)):
        out.append((tracks[i], score_transition(tracks[i - 1], tracks[i])))
    return out


def test_explanation_no_jargon_flags_duration_and_keys():
    from app.services.set_generator import _explanation
    tracks = [mk(bpm=120, key="8A"), mk(bpm=125, key="8A"), mk(bpm=130, key="2B")]  # ultima fuori chiave
    req = SetGenerationRequest(strategy="progressive", target_duration_minutes=90)
    exp = _explanation(_scored(tracks), req, total_seconds=1800)  # 30 min vs target 90
    assert "MVP" not in exp
    assert "120" in exp and "130" in exp                     # arco BPM
    assert "target" in exp.lower() or "durata" in exp.lower()  # avvisa durata lontana
    assert "brano 3" in exp                                   # segnala la transizione fuori chiave


def test_explanation_on_target_is_quiet_about_duration():
    from app.services.set_generator import _explanation
    tracks = [mk(bpm=124, key="8A"), mk(bpm=125, key="8A")]
    req = SetGenerationRequest(strategy="smooth", target_duration_minutes=30)
    exp = _explanation(_scored(tracks), req, total_seconds=1800)  # 30 min = target
    assert "target" not in exp.lower()
    assert "in chiave" in exp  # armonia OK dichiarata


# --- Fix 3) warning aggregati, durata come primo -----------------------------

def _ai_response(n):
    from app.schemas import AISetResponse, AITrackChoice
    return AISetResponse(
        set_title="X", global_explanation="g", missing_library_suggestions=[],
        tracks=[AITrackChoice(position=i, track_id=i, reason="r", transition_note="n", risk_level="low")
                for i in range(1, n + 1)],
    )


def test_validation_aggregates_repetitive_key_warnings():
    from app.services.validation import validate_ai_set
    cands = {1: mk(128, "8A", artist="A"), 2: mk(128, "2B", artist="B"),
             3: mk(128, "8A", artist="C"), 4: mk(128, "2B", artist="D")}
    for tid, t in cands.items():
        t.id = tid
    req = SetGenerationRequest(target_duration_minutes=20)  # 4x5min = 20, a target
    result = validate_ai_set(_ai_response(4), cands, req)
    key_warnings = [w for w in result.warnings if "chiave" in w.lower()]
    assert len(key_warnings) == 1                 # UN warning aggregato, non 3
    assert "2, 3, 4" in key_warnings[0]           # elenca le posizioni


def test_validation_duration_warning_comes_first():
    from app.services.validation import validate_ai_set
    cands = {1: mk(128, "8A", artist="A"), 2: mk(128, "9A", artist="B")}  # armonico
    for tid, t in cands.items():
        t.id = tid
    req = SetGenerationRequest(target_duration_minutes=60)  # 2x5min=10, ben sotto
    result = validate_ai_set(_ai_response(2), cands, req)
    assert result.warnings
    assert "durata" in result.warnings[0].lower()  # la durata è il warning primario


# --- Fix 6) export accurato + dedup ------------------------------------------

def _owned_set(db, specs):
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist
    pl = Playlist(platform="spotify", name="PL")
    db.add(pl)
    db.flush()
    for i, (bpm, key, artist, title) in enumerate(specs):
        t = Track(source_type="spotify", title=title, artist=artist, duration_seconds=300,
                  bpm=bpm, camelot_key=key, has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()
    return pl


def test_markdown_export_uses_mix_tip_not_raw_log(db):
    from app.routers.sets import export
    from app.services.set_generator import generate_set
    pl = _owned_set(db, [(124 + i * 0.5, "8A", f"A{i}", f"T{i}") for i in range(5)])
    sl = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=15))
    body = export(sl.id, format="markdown", db=db).body.decode()
    assert "differenza BPM" not in body   # niente log deterministico grezzo
    assert "beatmatch" in body or "pitch" in body or "mix armonico" in body  # consiglio di mix reale


def test_generator_drops_fuzzy_duplicate(db):
    # stessa traccia in due grafie (spazi/case/trattini): il set non la mette due volte
    from app.services.set_generator import generate_set
    pl = _owned_set(db, [
        (124.0, "8A", "Raär", "Sometimes I Hear Sirens"),
        (124.2, "8A", "Raar", "Raar - Sometimes I Hear Sirens"),  # duplicato fuzzy
        (125.0, "8A", "Other", "Different Track"),
        (126.0, "8A", "Third", "Another One"),
    ])
    sl = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=20,
                                               max_tracks_per_artist=5))
    titles = [st.track.title.lower() for st in sl.tracks]
    sirens = sum(1 for t in titles if "sometimes i hear sirens" in t)
    assert sirens <= 1  # non due volte lo stesso brano


# --- A1) export M3U8 per Rekordbox -------------------------------------------


def _set_with_paths(db, specs):
    """specs: (bpm, key, artist, title, local_path|None). local_path None = no file."""
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist
    pl = Playlist(platform="spotify", name="PL")
    db.add(pl)
    db.flush()
    for bpm, key, artist, title, path in specs:
        t = Track(source_type="spotify", title=title, artist=artist, duration_seconds=210,
                  bpm=bpm, camelot_key=key, has_local_file=path is not None, local_path=path)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()
    return pl


def test_m3u8_export_uses_local_paths_in_order(db):
    from app.routers.sets import export
    from app.services.set_generator import generate_set
    pl = _set_with_paths(db, [
        (124.0, "8A", "A0", "T0", "/music/a0.aiff"),
        (125.0, "8A", "A1", "T1", "/music/a1.aiff"),
        (126.0, "8A", "A2", "T2", "/music/a2.aiff"),
    ])
    sl = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=15))
    resp = export(sl.id, format="m3u8", db=db)
    body = resp.body.decode()
    lines = body.splitlines()
    assert lines[0] == "#EXTM3U"
    # ogni traccia: riga #EXTINF con durata e "artist — title", poi il path assoluto
    assert "#EXTINF:210,A0 — T0" in lines
    assert "#EXTINF:210,A1 — T1" in lines
    # i path compaiono nell'ordine reale del set (non quello d'inserimento)
    set_paths = [st.track.local_path for st in sl.tracks]
    m3u_paths = [ln for ln in lines if ln.startswith("/music/")]
    assert m3u_paths == set_paths
    # ogni #EXTINF è seguito immediatamente dal suo path
    i = lines.index("#EXTINF:210,A0 — T0")
    assert lines[i + 1] == "/music/a0.aiff"


def test_csv_export_includes_local_path(db):
    import csv as csvmod
    import io as iomod
    from app.routers.sets import export
    from app.services.set_generator import generate_set
    pl = _set_with_paths(db, [
        (124.0, "8A", "A0", "T0", "/music/a0.aiff"),
        (125.0, "8A", "A1", "T1", None),
        (126.0, "8A", "A2", "T2", "/music/a2.aiff"),
    ])
    sl = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=15,
                                               owned_only=False))
    body = export(sl.id, format="csv", db=db).body.decode()
    rows = list(csvmod.reader(iomod.StringIO(body)))
    header = rows[0]
    assert "local_path" in header
    idx = header.index("local_path")
    by_title = {row[header.index("title")]: row[idx] for row in rows[1:]}
    assert by_title["T0"] == "/music/a0.aiff"
    assert by_title["T1"] == ""             # nessun file locale -> stringa vuota
    assert by_title["T2"] == "/music/a2.aiff"


def test_m3u8_export_skips_tracks_without_file_with_comment(db):
    from app.routers.sets import export
    from app.services.set_generator import generate_set
    pl = _set_with_paths(db, [
        (124.0, "8A", "Owned0", "Has File 0", "/music/owned0.aiff"),
        (125.0, "8A", "Owned1", "Has File 1", "/music/owned1.aiff"),
        (126.0, "8A", "Owned2", "Has File 2", "/music/owned2.aiff"),
        (127.0, "8A", "Lead", "No File", None),
    ])
    sl = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=30,
                                               owned_only=False))
    body = export(sl.id, format="m3u8", db=db).body.decode()
    assert "/music/owned0.aiff" in body
    assert "No File" not in body           # la traccia senza file è esclusa
    assert "1 tracce senza file locale non incluse" in body  # commento con conteggio


# --- Fix 4) tab Transizioni: lente per classe --------------------------------

def test_transitions_lens_filters_by_class(db):
    from app.models import Track
    from app.routers.transitions import _ranked
    anchor = Track(source_type="spotify", title="anchor", bpm=128, camelot_key="8A",
                   energy=70, genre="techno", has_local_file=True)
    safe = Track(source_type="spotify", title="safe", bpm=129, camelot_key="9A",
                 energy=72, genre="techno", has_local_file=True)      # adiacente => sicura
    reset = Track(source_type="spotify", title="reset", bpm=128, camelot_key="2B",
                  energy=40, genre="ambient", has_local_file=True)     # calo energia => reset
    db.add_all([anchor, safe, reset])
    db.commit()

    only_reset = _ranked(db, anchor.id, limit=25, lens="good_reset")
    titles = {c.track.title for c in only_reset}
    assert "reset" in titles and "safe" not in titles

    unfiltered = _ranked(db, anchor.id, limit=25)
    assert {c.track.title for c in unfiltered} >= {"safe", "reset"}
