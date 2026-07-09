"""Genere come segnale di prima classe nella generazione dei set.

Due comportamenti:
1. `genre_similarity_score` conosce le famiglie di genere (techno/house/chill/...):
   sottogeneri della stessa famiglia sono coerenti anche senza token in comune,
   famiglie diverse sono un vero stacco, i super-generi ("Electronic") sono neutri.
2. Il ranking del set generator ha un termine di coerenza di genere DEDICATO
   (come l'arco di energia), non diluito nella media delle feature.
"""

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist
from app.schemas import SetGenerationRequest
from app.services.scoring import RESET_GENRE_SIMILARITY, genre_similarity_score
from app.services.set_generator import _DEFAULT_PROFILE, _candidate_score, generate_set


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


# --- similarita' per famiglie di genere ---------------------------------------


def test_same_family_scores_high_without_shared_tokens():
    # Stessa famiglia = stesso mondo sonoro, anche senza token in comune.
    assert genre_similarity_score("Techno", "Acid") >= 70
    assert genre_similarity_score("Ambient", "Downtempo") >= 70
    assert genre_similarity_score("House", "UK Garage") >= 70
    assert genre_similarity_score("Breakbeat", "Electro") >= 70


def test_subgenre_beats_family_sibling():
    # "Deep Techno" e' un sottogenere di Techno: piu' vicino di un cugino di famiglia.
    assert (genre_similarity_score("Deep Techno", "Techno")
            > genre_similarity_score("Techno", "Acid"))


def test_cross_family_is_below_reset_threshold():
    # Famiglie diverse: vero cambio di mondo sonoro -> deve valere come reset.
    assert genre_similarity_score("Techno", "House") < RESET_GENRE_SIMILARITY
    assert genre_similarity_score("Ambient", "Techno") < RESET_GENRE_SIMILARITY
    assert genre_similarity_score("Trance", "Drum & Bass") < RESET_GENRE_SIMILARITY


def test_umbrella_genre_is_neutral_not_a_clash():
    # "Electronic"/"Dance" sono super-generi: non devono valere come stacco.
    assert genre_similarity_score("Electronic", "Techno") >= RESET_GENRE_SIMILARITY
    assert genre_similarity_score("Dance", "House") >= RESET_GENRE_SIMILARITY
    # ...ma un super-genere resta meno coerente di una famiglia condivisa.
    assert (genre_similarity_score("Electronic", "Techno")
            < genre_similarity_score("Acid Techno", "Techno"))


def test_exact_match_and_missing_data_unchanged():
    assert genre_similarity_score("Techno", "Techno") == 100
    assert genre_similarity_score(None, "Techno") == 50
    assert genre_similarity_score(None, None) == 50


def test_unmapped_genres_fall_back_to_token_overlap():
    # Generi fuori mappa: resta la sovrapposizione token di prima.
    assert genre_similarity_score("Weirdcore", "Weirdcore Revival") > 50
    assert genre_similarity_score("Weirdcore", "Altrocore") <= 50


# --- termine dedicato nel ranking del generator --------------------------------


def test_genre_has_dedicated_weight_in_ranking():
    # A parita' di BPM/key/energia il genere deve spostare il ranking in modo
    # netto: termine con peso proprio, non diluito nella media con l'energia.
    req = SetGenerationRequest()
    prev = make_track(bpm=130, camelot_key="7A", energy=60, genre="Techno")
    same = make_track(bpm=130, camelot_key="7A", energy=65, genre="Acid Techno")
    other = make_track(bpm=130, camelot_key="7A", energy=65, genre="House")
    s_same, _ = _candidate_score(prev, same, 130.0, req, {}, _DEFAULT_PROFILE, 0.5)
    s_other, _ = _candidate_score(prev, other, 130.0, req, {}, _DEFAULT_PROFILE, 0.5)
    assert s_same - s_other > 10


def test_missing_genre_stays_neutral_in_ranking():
    # Una traccia senza genere non deve essere ne' premiata ne' punita rispetto
    # a una coerente: il termine usa il valore neutro (50), non sparisce.
    req = SetGenerationRequest()
    prev = make_track(bpm=130, camelot_key="7A", genre="Techno")
    unknown = make_track(bpm=130, camelot_key="7A", genre=None)
    clash = make_track(bpm=130, camelot_key="7A", genre="House")
    s_unknown, _ = _candidate_score(prev, unknown, 130.0, req, {}, _DEFAULT_PROFILE, 0.5)
    s_clash, _ = _candidate_score(prev, clash, 130.0, req, {}, _DEFAULT_PROFILE, 0.5)
    assert s_unknown > s_clash


def test_generated_set_groups_genres(db):
    # 2 techno + 2 house identiche per BPM/key/durata: il set deve raggruppare i
    # generi (1 solo cambio), non alternarli.
    pl = Playlist(platform="spotify", name="PL")
    db.add(pl)
    db.flush()
    genres = ["Techno", "House", "Techno", "House"]
    for i, g in enumerate(genres):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"Art{i}",
                  duration_seconds=200, bpm=126.0, camelot_key="8A", genre=g,
                  has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()

    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=13,
        start_bpm=126, end_bpm=126, max_tracks_per_artist=1,
    ))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    track_genres = []
    for st in ordered:
        track = db.get(Track, st.track_id)
        track_genres.append(track.genre)
    switches = sum(1 for a, b in zip(track_genres, track_genres[1:]) if a != b)
    assert switches == 1, f"generi alternati invece che raggruppati: {track_genres}"
