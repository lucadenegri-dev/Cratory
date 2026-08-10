"""review_genres: formato del prompt, tool web_search, allineamento output."""

import sys
import types

import pytest

from app.services import ai_tags


class _FakeParsed:
    def __init__(self, items):
        self.items = items


class _FakeResp:
    def __init__(self, items):
        self.parsed_output = _FakeParsed(items) if items is not None else None


def _install_fake_anthropic(monkeypatch, captured, items_out):
    class _FakeMessages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp(items_out)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_review_genres_empty_input_no_call():
    assert ai_tags.review_genres([]) == []


def test_review_genres_prompt_tools_and_alignment(monkeypatch):
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(genre="Tech House", confidence="high")])
    items = [{"artist": "ANNA", "title": "Hidden Beauties", "album": "EP1",
              "label": "Drumcode", "current_genre": "House",
              "candidates": ["Tech House", "Techno"]},
             {"artist": None, "title": None, "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    out = ai_tags.review_genres(items)
    # tool web_search presente con max_uses limitato
    assert captured["tools"] == [{"type": "web_search_20250305",
                                  "name": "web_search", "max_uses": 3}]
    assert captured["model"] == "claude-haiku-4-5"
    # il listato contiene i metadati e i candidati
    text = captured["messages"][0]["content"]
    assert "ANNA - Hidden Beauties" in text
    assert "genere attuale: House" in text
    assert "Tech House; Techno" in text
    # output allineato: il secondo item (mancante nella risposta) è None/low
    assert out == [{"genre": "Tech House", "confidence": "high"},
                   {"genre": None, "confidence": "low"}]


def test_review_genres_no_parsed_output_raises(monkeypatch):
    # Fix: se il modello non produce alcun output strutturato (parsing
    # fallito, o turno consumato interamente dalla ricerca web) la funzione
    # deve sollevare invece di restituire dei _Review() di default per ogni
    # item — altrimenti il batch tornerebbe tutto genre=None e verrebbe
    # marcato "revisionato" per errore (bug di resumabilità).
    captured = {}
    _install_fake_anthropic(monkeypatch, captured, None)
    with pytest.raises(ai_tags.AiReviewError):
        ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                "label": None, "current_genre": None,
                                "candidates": []}])


def test_review_genres_weird_confidence_becomes_low(monkeypatch):
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured, [ai_tags._Review(genre="Acid", confidence="boh")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "low"}]
