import unicodedata

from app.models import Track
from app.services.rekordbox_import import apply_collection

_XML = b"""<DJ_PLAYLISTS><COLLECTION>
<TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8A"
       Location="file://localhost/music/a.mp3"/>
</COLLECTION></DJ_PLAYLISTS>"""


def _owned(db, **kw):
    t = Track(source_type="spotify", has_local_file=True, **kw)
    db.add(t); db.commit(); db.refresh(t)
    return t


def test_apply_fills_bpm_key_and_energy_by_path(db):
    t = _owned(db, local_path="/music/a.mp3", genre="Techno")
    report = apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 128.0 and t.camelot_key == "8A"
    assert t.energy is not None            # ricalcolata da bpm+genere
    assert t.status == "ready_for_set"
    assert report["matched"] == 1 and report["bpm_set"] == 1


def test_apply_does_not_overwrite_existing_bpm(db):
    t = _owned(db, local_path="/music/a.mp3", bpm=120.0)
    apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 120.0                   # valore preesistente autorevole


def test_apply_overwrite_replaces_existing_bpm_and_key(db):
    """Con overwrite=True la ri-analisi Rekordbox vince sui valori esistenti
    (Rekordbox e' la fonte di verita' di BPM/key) e l'energia viene ricalcolata."""
    t = _owned(db, local_path="/music/a.mp3", bpm=120.0, camelot_key="5B",
               genre="Techno", energy=45, energy_source="estimated")
    report = apply_collection(db, _XML, overwrite=True)
    db.refresh(t)
    assert t.bpm == 128.0 and t.camelot_key == "8A"
    assert t.energy != 45                   # ricalcolata sul nuovo BPM
    assert report["bpm_set"] == 1 and report["key_set"] == 1


def test_apply_overwrite_does_not_blank_missing_rekordbox_values(db):
    """overwrite=True sovrascrive solo con valori presenti nell'XML: una riga
    senza AverageBpm/Tonality non deve azzerare i dati esistenti."""
    xml = b"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="Dreamscapes" Artist="SLV"
           Location="file://localhost/music/a.mp3"/>
    </COLLECTION></DJ_PLAYLISTS>"""
    t = _owned(db, local_path="/music/a.mp3", bpm=120.0, camelot_key="5B")
    apply_collection(db, xml, overwrite=True)
    db.refresh(t)
    assert t.bpm == 120.0 and t.camelot_key == "5B"


def test_apply_matches_by_artist_title_fallback(db):
    t = _owned(db, local_path="/other/path.mp3", artist="SLV", title="Dreamscapes")
    report = apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 128.0 and report["matched"] == 1


def test_apply_stores_canonical_camelot_from_lowercase_tonality(db):
    """M1: Tonality "8a" deve salvarsi come Camelot canonico "8A" (non la stringa
    grezza), cosi' le key combaciano con la normalizzazione del percorso manuale."""
    xml = b"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8a"
           Location="file://localhost/music/a.mp3"/>
    </COLLECTION></DJ_PLAYLISTS>"""
    t = _owned(db, local_path="/music/a.mp3")
    apply_collection(db, xml)
    db.refresh(t)
    assert t.camelot_key == "8A"


def test_apply_duplicate_rows_same_track_not_counted_unmatched(db):
    """M2: due righe XML che risolvono alla stessa traccia posseduta non devono
    gonfiare 'unmatched' (solo la prima e' "matched", la seconda e' un duplicato,
    ma nessuna delle due e' un mancato match)."""
    t = _owned(db, local_path="/music/a.mp3")
    xml = b"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8A"
           Location="file://localhost/music/a.mp3"/>
    <TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8A"
           Location="file://localhost/music/a.mp3"/>
    </COLLECTION></DJ_PLAYLISTS>"""
    report = apply_collection(db, xml)
    db.refresh(t)
    assert report["in_file"] == 2
    assert report["matched"] == 1
    assert report["unmatched"] == 0


def test_apply_matches_nfd_location_against_nfc_local_path(db):
    """M3: Rekordbox su macOS puo' esportare Location in NFD (es. 'e' + accento
    combinante); local_path indicizzato e' tipicamente NFC. Devono combaciare."""
    nfc_name = unicodedata.normalize("NFC", "Café Track.mp3")   # "é" precomposta
    nfd_name = unicodedata.normalize("NFD", nfc_name)                 # "e" + combining acute
    assert nfc_name != nfd_name  # sanity: le due forme sono byte-diverse

    t = _owned(db, local_path=f"/music/{nfc_name}")
    xml = f"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="Cafe Track" Artist="SLV" AverageBpm="128.00" Tonality="8A"
           Location="file://localhost/music/{nfd_name}"/>
    </COLLECTION></DJ_PLAYLISTS>""".encode("utf-8")
    report = apply_collection(db, xml)
    db.refresh(t)
    assert report["matched"] == 1
    assert t.bpm == 128.0


def test_match_skips_audio_hash_when_basename_not_owned(db, monkeypatch, tmp_path):
    """I1: se il basename della riga Rekordbox non appartiene a nessuna traccia
    posseduta, audio_hash NON deve essere invocato (evita un decode ffmpeg per
    ogni riga non posseduta: costoso e inutile perche' il fallback hash serve solo
    per "stesso file spostato", caso in cui il nome file sopravvive quasi sempre)."""
    from app.services import rekordbox_import

    called = []

    def _boom(path):
        called.append(path)
        raise AssertionError("audio_hash non deve essere chiamato per righe non possedute")

    monkeypatch.setattr(rekordbox_import, "audio_hash", _boom)

    real_file = tmp_path / "not_owned.mp3"
    real_file.write_bytes(b"fake-audio")
    _owned(db, local_path="/music/owned_other_name.mp3")

    xml = f"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="Unrelated" Artist="Z" AverageBpm="120.00" Tonality="5A"
           Location="file://localhost{real_file}"/>
    </COLLECTION></DJ_PLAYLISTS>""".encode("utf-8")
    report = apply_collection(db, xml)
    assert called == []
    assert report["matched"] == 0
