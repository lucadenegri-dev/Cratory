"""ShazamioRecognizer: riuso di loop+client tra segmenti e timeout per chiamata (E12).

Prima della fix, `recognize_file` creava un nuovo event loop + un nuovo `Shazam()`
per OGNI segmento (via `asyncio.run`) e non aveva timeout: un riconoscimento
bloccato impallava l'intero job. Qui `shazamio.Shazam` e' monkeypatchato con un
finto client asincrono, senza rete ne' audio.
"""

import asyncio

import pytest

import app.integrations.shazam as shazam_mod
from app.integrations.shazam import RecognizerError, ShazamioRecognizer

RAW_MATCH = {"track": {
    "title": "Strobe", "subtitle": "deadmau5", "isrc": None,
    "hub": {"actions": []},
}}


class _FakeShazamCounting:
    """Conta quante volte viene istanziato: deve succedere una sola volta per recognizer."""
    instances = 0

    def __init__(self, *a, **kw):
        _FakeShazamCounting.instances += 1

    async def recognize(self, path):
        return RAW_MATCH


class _FakeShazamSlow:
    """Non risponde mai entro il timeout."""

    async def recognize(self, path):
        await asyncio.sleep(10)
        return RAW_MATCH


class _FakeShazamMixed:
    """Prima chiamata lenta (va in timeout), seconda chiamata normale."""
    calls = 0

    async def recognize(self, path):
        _FakeShazamMixed.calls += 1
        if _FakeShazamMixed.calls == 1:
            await asyncio.sleep(10)
        return RAW_MATCH


def test_recognize_file_riusa_loop_e_client_tra_segmenti(monkeypatch):
    _FakeShazamCounting.instances = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamCounting)

    rec = ShazamioRecognizer()
    try:
        out1 = rec.recognize_file("seg_0.wav")
        out2 = rec.recognize_file("seg_12.wav")
    finally:
        rec.close()

    assert _FakeShazamCounting.instances == 1  # un solo client per tutti i segmenti
    assert out1["artist"] == "deadmau5" and out2["title"] == "Strobe"


def test_recognize_file_timeout_solleva_recognizer_error(monkeypatch):
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamSlow)
    monkeypatch.setattr(shazam_mod, "RECOGNIZE_TIMEOUT", 0.05)

    rec = ShazamioRecognizer()
    try:
        with pytest.raises(RecognizerError):
            rec.recognize_file("seg_0.wav")
    finally:
        rec.close()


def test_loop_non_avvelenato_dopo_timeout(monkeypatch):
    _FakeShazamMixed.calls = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamMixed)
    monkeypatch.setattr(shazam_mod, "RECOGNIZE_TIMEOUT", 0.05)

    rec = ShazamioRecognizer()
    try:
        with pytest.raises(RecognizerError):
            rec.recognize_file("seg_0.wav")  # va in timeout

        out = rec.recognize_file("seg_12.wav")  # il loop riusato deve funzionare ancora
    finally:
        rec.close()

    assert out["artist"] == "deadmau5"


def test_close_e_idempotente_e_permette_riuso_successivo(monkeypatch):
    _FakeShazamCounting.instances = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamCounting)

    rec = ShazamioRecognizer()
    rec.recognize_file("seg_0.wav")
    rec.close()
    rec.close()  # non deve sollevare

    # dopo close(), una nuova chiamata ricrea loop+client (nuova istanza, non un crash)
    out = rec.recognize_file("seg_12.wav")
    rec.close()

    assert _FakeShazamCounting.instances == 2
    assert out["title"] == "Strobe"
