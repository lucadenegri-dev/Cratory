"""Test Discovery mode: import idempotente (usato dal dig) + dig "Scava" (Discogs)."""

import pytest


def test_add_discovered_track_to_library(db):
    from app.models import Track
    from app.services.playlist_import import import_single_track

    track, created = import_single_track(
        db, platform="spotify", platform_track_id="sp1", title="Fresh Cut",
        artist="NewBand", isrc="USNEW0000001", duration_seconds=240, artwork_url="http://img",
    )
    assert created is True
    assert track.id is not None
    assert track.spotify_id == "sp1"
    assert track.source_type == "spotify"
    assert track.playlist_id is None  # entra in libreria, non legata a una playlist

    # idempotente: stesso ISRC -> stessa traccia, nessun duplicato
    again, created2 = import_single_track(
        db, platform="spotify", platform_track_id="sp1", title="Fresh Cut",
        artist="NewBand", isrc="USNEW0000001",
    )
    assert created2 is False
    assert again.id == track.id
    assert db.query(Track).count() == 1


def test_add_unresolved_track_dedup_by_name(db):
    """Un candidato senza ISRC/spotify_id aggiunto due volte non duplica (match per nome)."""
    from app.models import Track
    from app.services.playlist_import import import_single_track

    t1, c1 = import_single_track(db, platform="manual", title="Untitled", artist="Ghost")
    t2, c2 = import_single_track(db, platform="manual", title="Untitled", artist="Ghost")
    assert c1 is True and c2 is False
    assert t1.id == t2.id
    assert db.query(Track).count() == 1


# --- Task 4: router dig — reasons in output, taste_playlist_id in input -------

from app.integrations.discogs import DiscogsClient, DiscogsError
from app.models import Track
from app.routers.discovery import dig_endpoint
from app.schemas import DiscoveryDigRequest


def _fake_release(title, *, label="Lbl", style="Acid House", have=3, want=120):
    return {
        "id": 1, "title": title, "year": 2024,
        "label": [label], "style": [style],
        "community": {"have": have, "want": want}, "format": ["Vinyl"],
        "uri": "/release/1", "cover_image": "http://img",
    }


def _stub_pile(monkeypatch, items=100):
    """Mocka la sonda `count_releases`, che il dig chiama SEMPRE prima della search.
    Senza, questi test farebbero una richiesta VERA a Discogs (test senza rete: vedi
    il docstring di app/integrations/discogs.py). Default 100 = una pagina sola: pila
    corta, la finestra e' l'intera pila e `depth` non entra in cio' che questi test
    dimostrano (reason, badge, gusto). Deve essere > 0, o il dig si ferma prima della
    search e non ci sarebbero lead."""
    monkeypatch.setattr(DiscogsClient, "count_releases", lambda self, **kw: items)


def test_dig_endpoint_returns_reasons(db, monkeypatch):
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [_fake_release("Cult - Grail")],
    )
    _stub_pile(monkeypatch)
    resp = dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    assert resp.leads, "atteso almeno un lead"
    codes = {r.code for r in resp.leads[0].reasons}
    assert "rare_wanted" in codes and "deep_cut" in codes


def test_format_badge_priority():
    # `_format_badge` e' Discogs-specifico (have/want, format Discogs): si e' spostato
    # in `dig_sources/discogs.py` col seam del Task 1.
    from app.services.dig_sources.discogs import _format_badge

    assert _format_badge({"vinyl", "ep"}) == "EP"
    assert _format_badge({"vinyl", "lp", "album"}) == "LP"  # LP ha priorità su Album
    assert _format_badge({"vinyl", "12\""}) == '12"'
    assert _format_badge({"vinyl"}) is None
    assert _format_badge(set()) is None
    # Regressione: match ESATTO, non per sostringa. Una ristampa LP ha il
    # descrittore "repress" che CONTIENE "ep" — non deve diventare "EP".
    assert _format_badge({"vinyl", "lp", "album", "repress"}) == "LP"


def test_dig_endpoint_exposes_discogs_id_and_format_badge(db, monkeypatch):
    release = {
        "id": 42, "title": "Cult - Grail", "year": 2024,
        "label": ["Lbl"], "style": ["Acid House"],
        "community": {"have": 3, "want": 120}, "format": ["Vinyl", "EP"],
        "uri": "/release/42", "cover_image": "http://img",
    }
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [release],
    )
    _stub_pile(monkeypatch)
    resp = dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    lead = resp.leads[0]
    assert lead.discogs_id == 42
    assert lead.format_badge == "EP"


def test_dig_endpoint_ignores_legacy_taste_field_profile_is_library(db, monkeypatch):
    """Riscrittura SEMANTICA di `test_dig_endpoint_honors_taste_playlist_id`: la
    manopola del gusto e' stata rimossa (su 7 playlist su 10 azzerava l'ordinamento
    in silenzio — profilo quasi vuoto, perche' etichette e generi vengono dai tag dei
    file che i lead da streaming non hanno). Il campo legacy viene ignorato da
    Pydantic (nessun extra="forbid" su DiscoveryDigRequest) e il profilo arriva
    dalla LIBRERIA: la traccia in db aggancia i reason anche senza playlist.
    """
    t = Track(source_type="spotify", artist="Followed", title="Older",
              label="Warp", genre="Acid House")
    db.add(t)
    db.commit()

    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [_fake_release("Followed - New", label="Warp", style="Acid House")],
    )
    _stub_pile(monkeypatch)
    resp = dig_endpoint(
        DiscoveryDigRequest.model_validate(
            {"seed_type": "genre", "value": "Acid House", "taste_playlist_id": 999}
        ),
        db,
    )
    codes = {r.code for r in resp.leads[0].reasons}
    # style_match non e' piu' atteso: la release porta SOLO lo style del seme
    # ("Acid House" su un dig per "Acid House"), e il badge ora richiede affinita'
    # OLTRE il seme (_styles_beyond_seed). label_followed + artist_collected bastano
    # a provare cio' che questo test fissa: il profilo viene dalla libreria.
    assert {"label_followed", "artist_collected"} <= codes
    assert "style_match" not in codes


def test_dig_endpoint_502_on_discogs_error(db, monkeypatch):
    """Rate limit o token mancante NON devono sembrare 'zero risultati': il dig
    traduce DiscogsError in un 502 esplicito (stesso codice di get_release_detail,
    gia' tradotto dal frontend)."""
    from fastapi import HTTPException

    def _raise(self, **kw):
        raise DiscogsError("Discogs: rate limit (riprova piu' tardi o imposta DISCOGS_TOKEN).")

    monkeypatch.setattr(DiscogsClient, "search_releases", _raise)
    # La sonda deve RIUSCIRE: l'errore sotto test e' quello della search. Senza mock
    # la sonda fa una richiesta vera e, a rete assente, e' lei a sollevare DiscogsError:
    # il test passerebbe senza mai arrivare alla search, cioe' per il motivo sbagliato.
    _stub_pile(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == "discovery_provider_error"


# --- Task 3: GET /api/discovery/release/{discogs_id} — tracklist reale -------

_RELEASE_DETAIL = {
    "id": 249504,
    "title": "Selected Ambient Works 85-92",
    "artists": [{"name": "Aphex Twin (2)"}],
    "year": 1992,
    "labels": [{"name": "Apollo"}],
    "images": [{"type": "primary", "uri": "http://img/cover.jpg"}],
    "tracklist": [
        {"position": "A1", "type_": "track", "title": "Xtal", "duration": "4:56"},
        {"position": "", "type_": "heading", "title": "Side B"},
        {"position": "B1", "type_": "track", "title": "Tha", "duration": "4:35"},
        {"position": "B2", "type_": "track", "title": "Untitled", "duration": ""},
    ],
    "uri": "https://www.discogs.com/release/249504-Aphex-Twin-Selected-Ambient-Works-85-92",
}


def test_release_detail_normalizes_tracklist(db, monkeypatch):
    from app.routers.discovery import get_release_detail

    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: _RELEASE_DETAIL)
    out = get_release_detail(249504)
    assert out.discogs_id == 249504
    assert out.title == "Selected Ambient Works 85-92"
    assert out.artist == "Aphex Twin"  # suffisso di disambiguazione Discogs "(2)" rimosso
    assert out.label == "Apollo"
    assert out.thumb_url == "http://img/cover.jpg"
    assert out.discogs_url == _RELEASE_DETAIL["uri"]
    # la voce "heading" (Side B) e' esclusa: non e' una traccia
    assert [t.title for t in out.tracks] == ["Xtal", "Tha", "Untitled"]
    assert out.tracks[0].duration_seconds == 296  # "4:56" -> 4*60+56
    assert out.tracks[2].duration_seconds is None  # durata vuota -> None


def test_release_detail_502_on_discogs_error(monkeypatch):
    from fastapi import HTTPException
    from app.routers.discovery import get_release_detail

    def _raise(self, rid):
        raise DiscogsError("Discogs 500: boom")
    monkeypatch.setattr(DiscogsClient, "get_release", _raise)
    with pytest.raises(HTTPException) as exc_info:
        get_release_detail(249504)
    assert exc_info.value.status_code == 502


def test_release_detail_tolerates_image_and_label_without_keys(monkeypatch):
    """Un'immagine/etichetta Discogs priva della chiave attesa non deve far
    esplodere l'endpoint con un 500 grezzo: thumb_url/label degradano a None."""
    from app.routers.discovery import get_release_detail

    payload = {
        "id": 1, "title": "Rel", "artists": [{"name": "A"}],
        "images": [{"type": "primary"}],   # nessun "uri"
        "labels": [{"catno": "X-1"}],        # nessun "name"
        "tracklist": [{"position": "A1", "type_": "track", "title": "T", "duration": "3:00"}],
    }
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: payload)
    out = get_release_detail(1)
    assert out.thumb_url is None
    assert out.label is None
    assert [t.title for t in out.tracks] == ["T"]


# --- Task 4: playlist di sistema "Discovery" ----------------------------------


def test_get_or_create_discovery_playlist_is_idempotent(db):
    from app.services.playlist_import import get_or_create_discovery_playlist

    p1 = get_or_create_discovery_playlist(db)
    db.commit()
    p2 = get_or_create_discovery_playlist(db)
    assert p1.id == p2.id
    assert p1.name == "Discovery"
    assert p1.kind == "discovery"
    assert p1.platform == "manual"


# --- Task 5: POST /api/discovery/save-for-later ------------------------------


def test_save_for_later_imports_and_adds_to_discovery_playlist(db):
    from app.routers.discovery import save_for_later
    from app.schemas import DiscoverySaveForLaterRequest
    from app.services.playlist_import import get_or_create_discovery_playlist
    from app.repositories import tracks_for_playlist

    resp = save_for_later(DiscoverySaveForLaterRequest(
        artist="Voiron", title="Night Signal", duration_seconds=320,
    ), db)
    assert resp.created is True
    assert resp.track.title == "Night Signal"

    playlist = get_or_create_discovery_playlist(db)
    tracks = tracks_for_playlist(db, playlist.id)
    assert [t.title for t in tracks] == ["Night Signal"]

    # idempotente: stessa traccia (match per nome, niente ISRC/platform_track_id),
    # nessuna membership duplicata
    save_for_later(DiscoverySaveForLaterRequest(artist="Voiron", title="Night Signal"), db)
    assert len(tracks_for_playlist(db, playlist.id)) == 1
