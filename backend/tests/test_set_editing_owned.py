"""Editing disk-first: la garanzia "solo posseduti" sopravvive a replace/alternative.

Un set generato con owned_only=True non deve poter reintrodurre lead (tracce senza
file) tramite l'editor: il flag e' persistito sul Setlist e i servizi di editing
lo rispettano da soli, senza parametri extra dall'API.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401 - importa i modelli per registrarli
from app.db import Base, ensure_schema
from app.integrations import LLMClient
from app.models import Track
from app.repositories import all_playable_tracks, get_setlist
from app.schemas import SetGenerationRequest
from app.serializers import setlist_out
from app.services.ai_agent import generate_ai_set
from app.services.alternatives import find_alternatives
from app.services.set_editor import SetEditError, replace_track
from app.services.set_generator import generate_set


def _track(i: int, *, owned: bool | None, bpm: float | None = 128.0) -> Track:
    return Track(
        source_type="spotify", title=f"T{i}", artist=f"A{i}",
        bpm=bpm, camelot_key="8A", duration_seconds=300,
        has_local_file=owned,
    )


def _seed_owned(db, n: int = 6) -> None:
    """n tracce possedute con BPM vicini: con target 20min il set ne usa 4."""
    for i in range(1, n + 1):
        db.add(_track(i, owned=True, bpm=125.0 + i))
    db.commit()


def _gen(db, **kw):
    return generate_set(db, SetGenerationRequest(target_duration_minutes=20, **kw))


# --- Repository: pool suonabile filtrabile per possesso -----------------------


def test_all_playable_tracks_filtra_possedute(db):
    db.add(_track(1, owned=True))
    db.add(_track(2, owned=False))
    db.add(_track(3, owned=None))  # riga pre-migrazione: equivale a non posseduta
    db.add(_track(4, owned=True, bpm=None))  # senza BPM: mai suonabile
    db.commit()

    assert {t.title for t in all_playable_tracks(db)} == {"T1", "T2", "T3"}
    assert {t.title for t in all_playable_tracks(db, owned_only=True)} == {"T1"}


# --- Generazione: il flag resta sul set ---------------------------------------


def test_generate_set_persiste_owned_only(db):
    _seed_owned(db)

    s = _gen(db)  # default disk-first: owned_only=True
    assert get_setlist(db, s.id).owned_only is True

    s2 = _gen(db, owned_only=False)
    assert get_setlist(db, s2.id).owned_only is False


class _FakeLLM(LLMClient):
    """Sceglie le prime 4 candidate in ordine (niente rete/chiave)."""

    def complete_json(self, system_prompt, payload, schema):
        ids = [c["id"] for c in payload["candidate_tracks"][:4]]
        return {
            "set_title": "Set AI",
            "global_explanation": "spiegazione di prova",
            "tracks": [
                {"position": i + 1, "track_id": tid, "reason": "scelta",
                 "transition_note": "mix", "risk_level": "low"}
                for i, tid in enumerate(ids)
            ],
            "missing_library_suggestions": [],
        }


def test_ai_set_persiste_owned_only(db):
    _seed_owned(db)
    req = SetGenerationRequest(target_duration_minutes=20, prompt="set di prova", use_ai=True)
    s = generate_ai_set(db, req, _FakeLLM())
    assert get_setlist(db, s.id).owned_only is True


# --- Replace: niente lead in un set "solo posseduti" ---------------------------


def test_replace_rifiuta_lead_su_set_owned(db):
    _seed_owned(db)
    s = _gen(db)
    lead = _track(99, owned=False)
    db.add(lead)
    db.commit()

    with pytest.raises(SetEditError, match="possedut"):
        replace_track(db, s.id, 1, lead.id)


def test_replace_accetta_posseduta_su_set_owned(db):
    _seed_owned(db)
    s = _gen(db)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db, owned_only=True) if t.id not in present)

    out = replace_track(db, s.id, 1, spare.id)
    slot = sorted(out.tracks, key=lambda st: st.position)[0]
    assert slot.track_id == spare.id


def test_replace_accetta_lead_su_set_libero(db):
    _seed_owned(db)
    s = _gen(db, owned_only=False)
    lead = _track(99, owned=False)
    db.add(lead)
    db.commit()

    out = replace_track(db, s.id, 1, lead.id)
    assert any(st.track_id == lead.id for st in out.tracks)


# --- Alternative: il pool rispetta la garanzia del set --------------------------


def test_alternative_escludono_lead_su_set_owned(db):
    _seed_owned(db)  # 6 possedute: 4 nel set, 2 di scorta
    s = _gen(db)
    # lead molto compatibili: senza filtro finirebbero tra le proposte
    for i in range(90, 95):
        db.add(_track(i, owned=False))
    db.commit()

    alts = find_alternatives(db, s, position=2, mode="safer", limit=10)
    assert alts  # le possedute di scorta restano proponibili
    assert all(a.track.has_local_file for a in alts)


def test_alternative_vuote_se_restano_solo_lead(db):
    _seed_owned(db, n=4)  # il set usa tutte le possedute: le uniche scorte sono lead
    s = _gen(db)
    for i in range(90, 95):
        db.add(_track(i, owned=False))
    db.commit()

    assert find_alternatives(db, s, position=2, mode="safer", limit=5) == []


def test_alternative_includono_lead_su_set_libero(db):
    _seed_owned(db, n=4)
    s = _gen(db, owned_only=False)
    for i in range(90, 95):
        db.add(_track(i, owned=False))
    db.commit()

    alts = find_alternatives(db, s, position=2, mode="safer", limit=5)
    assert alts
    assert all(not a.track.has_local_file for a in alts)


# --- Schema/API: colonna migrata e flag esposto --------------------------------


def test_owned_only_su_schema_nuovo():
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("setlists")}
    assert "owned_only" in cols


def test_owned_only_su_db_esistente_senza_colonna():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE setlists RENAME TO _s"))
        # tabella minima pre-migrazione (senza owned_only)
        conn.execute(text("CREATE TABLE setlists (id INTEGER PRIMARY KEY, name VARCHAR)"))
        conn.execute(text("DROP TABLE _s"))
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("setlists")}
    assert "owned_only" in cols


def test_setlist_out_espone_owned_only(db):
    _seed_owned(db)
    s = _gen(db)
    assert setlist_out(get_setlist(db, s.id)).owned_only is True
