from dataclasses import dataclass

from app.services.match_distance import grade_confidence, weighted_distance


@dataclass
class FileStub:
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: int | None = None
    label: str | None = None


def _canon(**kw):
    # chiavi come le produce integrations/musicbrainz._parse_recording
    out = {}
    if "artist" in kw:
        out["canonical_artist"] = kw["artist"]
    if "title" in kw:
        out["canonical_title"] = kw["title"]
    if "album" in kw:
        out["canonical_album"] = kw["album"]
    if "label" in kw:
        out["label"] = kw["label"]
    if "release_date" in kw:
        out["release_date"] = kw["release_date"]
    return out


def test_exact_is_strong_even_with_divergent_tags():
    f = FileStub(artist="wrong", title="totally different")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=True) == "strong"


def test_text_perfect_match_is_strong():
    f = FileStub(artist="Daft Punk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_text_strong_divergence_is_weak():
    f = FileStub(artist="Someone Else", title="A Completely Other Song")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "weak"


def test_the_article_and_feat_do_not_penalize():
    f = FileStub(artist="The Prodigy feat. Someone", title="Firestarter")
    c = _canon(artist="Prodigy", title="Firestarter")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_case_and_punctuation_are_ignored():
    f = FileStub(artist="DAFT PUNK!!!", title="around, the world")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_missing_secondary_fields_are_not_penalized():
    # file senza album/year/label: contano solo artist+title (ancore)
    f = FileStub(artist="Daft Punk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World",
               album="Homework", release_date="1997", label="Virgin")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_no_comparable_fields_is_weak():
    f = FileStub()  # nessun tag
    c = _canon(artist="Daft Punk", title="Around the World")
    assert weighted_distance(f, c) is None
    assert grade_confidence(f, c, exact=False) == "weak"


def test_single_typo_stays_strong():
    # un solo refuso su un'ancora, l'altra perfetta -> match forte
    f = FileStub(artist="Daft Bunk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_moderate_divergence_is_medium():
    # artist giusto ma title sostanzialmente diverso -> da rivedere (medium)
    f = FileStub(artist="Daft Punk", title="Harder Better")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "medium"
