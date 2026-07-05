"""Anello AI del genere in batch: una chiamata LLM per chunk, cache anche dei null.

Sostituisce la vecchia chiamata per-traccia (N round-trip sequenziali): le tracce
senza genere vengono raggruppate in chunk da genre_ai.BATCH_SIZE per una sola
chiamata LLM ciascuno. L'esito viene cachato in EnrichmentCache (provider
"genre_ai"), null compreso ("il modello non conosce il brano"), cosi' non si
richiede all'infinito. I chunk falliti per errore LLM NON vengono cachati.
"""
import types

from app.core import config


class _FakeLLM:
    """Client LLM finto: risponde per ogni traccia del payload via `genre_fn`."""

    def __init__(self, genre_fn):
        self.calls = []
        self.genre_fn = genre_fn

    def complete_json(self, system, payload, schema):
        self.calls.append(payload)
        return {"items": [
            {"index": it["index"], "genre": self.genre_fn(it)}
            for it in payload["tracks"]
        ]}


def _stub_track(i, title=None, artist="Artist"):
    return types.SimpleNamespace(
        id=i, artist=artist, title=title or f"Track {i}", label=None, year=None,
    )


# --- genre_ai.suggest_genres ---------------------------------------------------


def test_suggest_genres_una_chiamata_per_chunk(monkeypatch):
    from app.services import genre_ai

    monkeypatch.setattr(config.settings, "ai_api_key", "test-key")
    fake = _FakeLLM(lambda it: None if it["title"] == "Unknown" else "tech-house")
    monkeypatch.setattr(genre_ai, "get_llm_client", lambda: fake)

    out = genre_ai.suggest_genres([_stub_track(1), _stub_track(2, title="Unknown")])
    assert len(fake.calls) == 1  # un solo round-trip per tutto il chunk
    assert out == {1: "Tech House", 2: None}  # genere normalizzato, null preservato


def test_suggest_genres_chunk_su_batch_grandi(monkeypatch):
    from app.services import genre_ai

    monkeypatch.setattr(config.settings, "ai_api_key", "test-key")
    fake = _FakeLLM(lambda it: "techno")
    monkeypatch.setattr(genre_ai, "get_llm_client", lambda: fake)

    n = genre_ai.BATCH_SIZE + 5
    out = genre_ai.suggest_genres([_stub_track(i) for i in range(n)])
    assert len(fake.calls) == 2
    assert len(out) == n
    assert set(out.values()) == {"Techno"}


def test_suggest_genres_errore_llm_chunk_saltato(monkeypatch):
    """Errore LLM -> chunk saltato senza crash: nessun dato, nessuna invenzione."""
    from app.integrations.llm import LLMError
    from app.services import genre_ai

    monkeypatch.setattr(config.settings, "ai_api_key", "test-key")

    class _Boom:
        def complete_json(self, *a, **k):
            raise LLMError("giu'")

    monkeypatch.setattr(genre_ai, "get_llm_client", lambda: _Boom())
    assert genre_ai.suggest_genres([_stub_track(1)]) == {}


def test_suggest_genres_non_configurata():
    """Senza AI_API_KEY (fixture autouse): dizionario vuoto, zero tentativi."""
    from app.services import genre_ai

    assert genre_ai.suggest_genres([_stub_track(1)]) == {}


def test_suggest_genres_ignora_tracce_senza_identita(monkeypatch):
    from app.services import genre_ai

    monkeypatch.setattr(config.settings, "ai_api_key", "test-key")
    fake = _FakeLLM(lambda it: "house")
    monkeypatch.setattr(genre_ai, "get_llm_client", lambda: fake)

    out = genre_ai.suggest_genres([
        _stub_track(1),
        types.SimpleNamespace(id=2, artist=None, title="T", label=None, year=None),
    ])
    assert out == {1: "House"}  # la traccia senza artista non viene chiesta


# --- passata AI dentro enrich_features ------------------------------------------


class _CoreProvider:
    """Provider stub: bpm+key, mai genere (il genere resta all'anello AI)."""

    name = "core"

    def lookup(self, **kw):
        return {"bpm": 128.0, "camelot_key": "8A", "confidence": 80}


def _reset_core(db, *tracks):
    """Rimette le tracce nel batch di enrichment (bpm mancante)."""
    for t in tracks:
        t.bpm = None
        t.camelot_key = None
    db.commit()


def test_enrich_features_genere_ai_in_batch_con_cache(db, monkeypatch):
    from app.models import EnrichmentCache, Track
    from app.services import feature_enrichment, genre_ai

    t1 = Track(source_type="spotify", title="T1", artist="A")
    t2 = Track(source_type="spotify", title="T2", artist="B")
    t3 = Track(source_type="spotify", title="T3", artist="C",
               genre="House", genre_source="provider")
    db.add_all([t1, t2, t3])
    db.commit()

    calls: list[list[int]] = []

    def fake_suggest(tracks):
        calls.append(sorted(t.id for t in tracks))
        return {t1.id: "Techno", t2.id: None}

    monkeypatch.setattr(genre_ai, "suggest_genres", fake_suggest)

    r = feature_enrichment.enrich_features(db, _CoreProvider())
    assert calls == [[t1.id, t2.id]]  # t3 ha gia' un genere: mai chiesta all'AI
    assert t1.genre == "Techno" and t1.genre_source == "ai"
    assert t2.genre is None
    assert t3.genre == "House" and t3.genre_source == "provider"
    assert r["ai_genres"] == 1

    rows = db.query(EnrichmentCache).filter_by(provider="genre_ai").all()
    assert {row.result_json["genre"] for row in rows} == {"Techno", None}

    # Secondo run: genere dalla cache (anche il null), zero nuove chiamate AI.
    t1.genre = None
    t1.genre_source = None
    _reset_core(db, t1, t2)
    feature_enrichment.enrich_features(db, _CoreProvider())
    assert len(calls) == 1
    assert t1.genre == "Techno" and t1.genre_source == "ai"
    assert t2.genre is None

    # force=True bypassa la cache AI in lettura: si richiede.
    t1.genre = None
    t1.genre_source = None
    feature_enrichment.enrich_features(db, _CoreProvider(), force=True,
                                       track_ids=[t1.id, t2.id])
    assert len(calls) == 2


def test_enrich_features_ai_fallita_non_cachea(db, monkeypatch):
    """Chunk fallito (o AI non configurata) -> niente cache -> ritentato al run dopo."""
    from app.models import EnrichmentCache, Track
    from app.services import feature_enrichment, genre_ai

    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.commit()

    calls = []
    monkeypatch.setattr(genre_ai, "suggest_genres",
                        lambda tracks: (calls.append(1), {})[1])

    feature_enrichment.enrich_features(db, _CoreProvider())
    assert calls == [1]
    assert db.query(EnrichmentCache).filter_by(provider="genre_ai").count() == 0

    _reset_core(db, t)
    feature_enrichment.enrich_features(db, _CoreProvider())
    assert calls == [1, 1]  # nessuna cache: la traccia viene richiesta


def test_enrich_features_fase_genre_ai_nel_progress(db, monkeypatch):
    from app.models import Track
    from app.services import feature_enrichment, genre_ai

    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.commit()
    monkeypatch.setattr(genre_ai, "suggest_genres", lambda tracks: {t.id: "Techno"})

    phases = []
    feature_enrichment.enrich_features(
        db, _CoreProvider(), on_progress=lambda i, tot, ph: phases.append(ph),
    )
    assert "feature" in phases
    assert "genre_ai" in phases


def test_energy_proxy_usa_genere_ai(db, monkeypatch):
    """L'energia stimata deve vedere il genere AI (bias di genere nel proxy)."""
    from app.models import Track
    from app.services import feature_enrichment, genre_ai
    from app.services.feature_enrichment import estimate_energy

    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.commit()
    monkeypatch.setattr(genre_ai, "suggest_genres", lambda tracks: {t.id: "Techno"})

    feature_enrichment.enrich_features(db, _CoreProvider())
    assert t.energy == estimate_energy(128.0, None, "Techno")
    assert t.energy > estimate_energy(128.0, None, None)  # il bias e' entrato
