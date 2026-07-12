"""A16: expand deve scartare i candidati che possiedi già anche in una variante
diversa ('Strobe' vs 'Strobe (Original Mix)'), riusando la chiave di dedup del dig."""
from app.models import Track
from app.services.discovery import DiscoveryCandidate, _drop_in_library, _key


def _cand(artist, title):
    return DiscoveryCandidate(artist=artist, title=title, match=0.9, source="similar_artist")


def test_owned_variant_drops_plain_candidate(db):
    library = [Track(artist="Deadmau5", title="Strobe (Original Mix)", has_local_file=True)]
    cands = {
        _key("Deadmau5", "Strobe"): _cand("Deadmau5", "Strobe"),
        _key("Deadmau5", "Strobe (Radio Edit)"): _cand("Deadmau5", "Strobe (Radio Edit)"),
    }
    out = _drop_in_library(cands, library)
    assert out == [], "le varianti di un brano posseduto vanno scartate"


def test_different_track_is_kept(db):
    library = [Track(artist="Deadmau5", title="Strobe (Original Mix)", has_local_file=True)]
    cands = {_key("Deadmau5", "Ghosts n Stuff"): _cand("Deadmau5", "Ghosts n Stuff")}
    out = _drop_in_library(cands, library)
    assert [c.title for c in out] == ["Ghosts n Stuff"]
