from app.services.rekordbox_import import parse_collection

_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <COLLECTION Entries="2">
    <TRACK TrackID="1" Name="Dreamscapes" Artist="SLV" AverageBpm="128.00"
           Tonality="8A" Location="file://localhost/Users/luca/Music/SLV%20-%20Dreamscapes.mp3"/>
    <TRACK TrackID="2" Name="NoKey" Artist="X" AverageBpm="0.00" Tonality=""
           Location="file://localhost/Users/luca/Music/x.mp3"/>
  </COLLECTION>
</DJ_PLAYLISTS>"""


def test_parse_collection_decodes_location_and_key():
    tracks = parse_collection(_XML)
    assert len(tracks) == 2
    t = tracks[0]
    assert t.path == "/Users/luca/Music/SLV - Dreamscapes.mp3"
    assert t.bpm == 128.0
    assert t.camelot == "8A"
    assert t.artist == "SLV" and t.title == "Dreamscapes"


def test_parse_collection_null_bpm_and_key():
    t = parse_collection(_XML)[1]
    assert t.bpm is None       # AverageBpm 0.00 → None
    assert t.camelot is None   # Tonality vuota → None


def test_parse_collection_normalizes_lowercase_tonality_to_canonical_camelot():
    """Tonality "8a" (minuscolo, come talvolta esporta Rekordbox) deve normalizzare
    in Camelot canonico "8A", cosi' le key combaciano col percorso manuale."""
    xml = b"""<DJ_PLAYLISTS><COLLECTION>
    <TRACK Name="T" Artist="A" AverageBpm="120.00" Tonality="8a"
           Location="file://localhost/music/t.mp3"/>
    </COLLECTION></DJ_PLAYLISTS>"""
    t = parse_collection(xml)[0]
    assert t.camelot == "8A"
