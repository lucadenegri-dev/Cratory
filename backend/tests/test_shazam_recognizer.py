"""ShazamioRecognizer: riuso di loop+client, timeout, pacing e backoff con ripresa.

`shazamio.Shazam` e' monkeypatchato con un finto client asincrono, senza rete ne'
audio; `sleep`/`monotonic` sono iniettati finti, cosi' pacing e backoff si
verificano senza dormire davvero.
"""

import asyncio

import pytest

import app.integrations.shazam as shazam_mod
from app.integrations.shazam import BACKOFF_WAITS, MIN_CALL_INTERVAL, RecognizerError, ShazamioRecognizer

RAW_MATCH = {"track": {
    "title": "Strobe", "subtitle": "deadmau5", "isrc": None,
    "hub": {"actions": []},
}}


class _FakeClock:
    """Orologio finto: lo sleep iniettato lo fa avanzare, cosi' il pacing e'
    verificabile deterministicamente."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def _recognizer(clock):
    return ShazamioRecognizer(sleep=clock.sleep, monotonic=clock.monotonic)


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
    """Prima chiamata lenta (va in timeout), poi normale."""
    calls = 0

    async def recognize(self, path):
        _FakeShazamMixed.calls += 1
        if _FakeShazamMixed.calls == 1:
            await asyncio.sleep(10)
        return RAW_MATCH


def test_recognize_file_riusa_loop_e_client_tra_segmenti(monkeypatch):
    _FakeShazamCounting.instances = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamCounting)

    clock = _FakeClock()
    rec = _recognizer(clock)
    try:
        out1 = rec.recognize_file("seg_0.wav")
        out2 = rec.recognize_file("seg_12.wav")
    finally:
        rec.close()

    assert _FakeShazamCounting.instances == 1  # un solo client per tutti i segmenti
    assert out1["artist"] == "deadmau5" and out2["title"] == "Strobe"


def test_pacing_tra_chiamate_ravvicinate(monkeypatch):
    # due riconoscimenti back-to-back: il secondo aspetta MIN_CALL_INTERVAL
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamCounting)

    clock = _FakeClock()
    rec = _recognizer(clock)
    try:
        rec.recognize_file("seg_0.wav")
        rec.recognize_file("seg_12.wav")
    finally:
        rec.close()

    assert clock.sleeps == [MIN_CALL_INTERVAL]  # solo il pacing della seconda chiamata


def test_backoff_poi_recognizer_error_se_il_guasto_persiste(monkeypatch):
    # endpoint sempre in timeout: ritenta con attese crescenti, poi dichiara errore
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamSlow)
    monkeypatch.setattr(shazam_mod, "RECOGNIZE_TIMEOUT", 0.05)

    clock = _FakeClock()
    rec = _recognizer(clock)
    try:
        with pytest.raises(RecognizerError):
            rec.recognize_file("seg_0.wav")
    finally:
        rec.close()

    # tutte le attese di backoff sono state fatte (il pacing puo' aggiungersi in mezzo)
    assert [s for s in clock.sleeps if s in BACKOFF_WAITS] == list(BACKOFF_WAITS)


def test_backoff_recupera_un_timeout_transitorio(monkeypatch):
    # primo tentativo in timeout, il retry interno riesce: nessun errore verso il core
    _FakeShazamMixed.calls = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamMixed)
    monkeypatch.setattr(shazam_mod, "RECOGNIZE_TIMEOUT", 0.05)

    clock = _FakeClock()
    rec = _recognizer(clock)
    try:
        out = rec.recognize_file("seg_0.wav")
    finally:
        rec.close()

    assert out["artist"] == "deadmau5"
    assert BACKOFF_WAITS[0] in clock.sleeps       # ha aspettato prima di riprovare
    assert BACKOFF_WAITS[1] not in clock.sleeps   # ma un solo retry e' bastato


def test_close_e_idempotente_e_permette_riuso_successivo(monkeypatch):
    _FakeShazamCounting.instances = 0
    monkeypatch.setattr("shazamio.Shazam", _FakeShazamCounting)

    clock = _FakeClock()
    rec = _recognizer(clock)
    rec.recognize_file("seg_0.wav")
    rec.close()
    rec.close()  # non deve sollevare

    # dopo close(), una nuova chiamata ricrea loop+client (nuova istanza, non un crash)
    out = rec.recognize_file("seg_12.wav")
    rec.close()

    assert _FakeShazamCounting.instances == 2
    assert out["title"] == "Strobe"
