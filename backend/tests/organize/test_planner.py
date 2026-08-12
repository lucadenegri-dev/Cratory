import unicodedata

from app.organize.models import Issue
from app.organize.services.planner import build_plan, render_destination, effective_tags
from tests.organize.conftest import make_audio_file

SNAP = {"naming_template": "{artist} - {title}", "folder_template": "{genre}/{artist}"}
TARGET_ROOT = "/lib"


def _accepted(file_id, field, to=None, action="retag"):
    fix = {"field": field, "action": action}
    if to is not None:
        fix["to"] = to
    return Issue(file_id=file_id, type="x", field=field, severity="warning",
                 detail="", suggested_fix_json=fix, status="accepted")


def test_retag_aggregates_per_file():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="bel titolo", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGET_ROOT)
    retag = [o for o in ops if o.kind == "RETAG"]
    assert len(retag) == 1
    assert retag[0].before == {"artist": "PINCO"} and retag[0].after == {"artist": "Pinco"}


def test_effective_tags_used_in_rename():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="T", genre="House",
                        path="/lib/old.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGET_ROOT)
    move = [o for o in ops if o.kind in ("RENAME", "MOVE")][0]
    assert move.after["path"] == "/lib/House/Pinco/Pinco - T.mp3"  # usa l'artist corretto


def test_rename_vs_move():
    # già in /lib/House/A, cambia solo il nome → RENAME
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/House/A/vecchio.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert ops[0].kind == "RENAME" and ops[0].after["path"] == "/lib/House/A/A - T.mp3"


def test_move_to_different_folder():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert ops[0].kind == "MOVE"


def test_removed_file_only_delete():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], {1}, SNAP, TARGET_ROOT)
    assert [o.kind for o in ops] == ["DELETE"]
    assert ops[0].before == {"path": "/lib/varie/x.mp3"}


def test_sanitize_path_chars():
    f = make_audio_file(1, root_id=1, artist="AC/DC", title="T", genre="Rock",
                        path="/lib/x.mp3", ext="mp3")
    dest, miss = render_destination(f, effective_tags(f, []), SNAP, TARGET_ROOT)
    assert "AC_DC" in dest and ".." not in dest


def test_missing_field_no_op():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert ops == []  # genre mancante per {genre}/... → nessuna rinomina


def test_removed_file_with_fix_only_delete():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="T", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], {1}, SNAP, TARGET_ROOT)
    assert [o.kind for o in ops] == ["DELETE"]


def test_order_and_determinism():
    keep = make_audio_file(1, root_id=1, artist="vecchio", title="T", genre="House",
                           path="/lib/varie/a.mp3", ext="mp3")
    rem = make_audio_file(2, root_id=1, artist="B", title="U", genre="House",
                          path="/lib/varie/b.mp3", ext="mp3")
    ops = build_plan([keep, rem], [_accepted(1, "artist", "A")], {2}, SNAP, TARGET_ROOT)
    assert [o.kind for o in ops] == ["RETAG", "MOVE", "DELETE"]
    assert build_plan([rem, keep], [_accepted(1, "artist", "A")], {2}, SNAP, TARGET_ROOT) == ops


def test_no_op_when_path_differs_only_by_unicode_form():
    # Il file è già al posto giusto, ma il nome su disco è in forma NFD mentre
    # i tag rendono NFC (macOS/APFS li considera lo STESSO file). Non deve
    # generare una RINOMINA fantasma che si ripete all'infinito.
    nfd_path = unicodedata.normalize("NFD", "/lib/House/Café/Café - T.mp3")
    f = make_audio_file(1, root_id=1, artist="Café", title="T", genre="House",
                        path=nfd_path, ext="mp3")
    assert unicodedata.is_normalized("NFD", f.path)  # il path resta NFD
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert ops == []


def test_no_op_when_folder_differs_only_by_case():
    # Cartella su disco 'Electronic', tag genere 'electronic': su un FS
    # case-insensitive (APFS) è la stessa cartella → nessuno SPOSTAMENTO.
    f = make_audio_file(1, root_id=1, artist="Arca", title="Time", genre="electronic",
                        path="/lib/Electronic/Arca/Arca - Time.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert ops == []


def test_genuine_move_still_emitted_despite_normalization():
    # Regressione: una destinazione realmente diversa deve comunque produrre MOVE.
    f = make_audio_file(1, root_id=1, artist="Arca", title="Time", genre="Techno",
                        path="/lib/Electronic/Arca/Arca - Time.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGET_ROOT)
    assert [o.kind for o in ops] == ["MOVE"]
    assert ops[0].after["path"] == "/lib/Techno/Arca/Arca - Time.mp3"


def test_no_op_retag_when_tag_already_correct():
    # Fix già applicato in un giro precedente: il tag ha già il valore target.
    # Non deve rigenerare un RETAG fantasma (la issue resta 'accepted' per sempre).
    f = make_audio_file(1, root_id=1, artist="Hermeth", title="T", genre="House",
                        path="/lib/House/Hermeth/Hermeth - T.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Hermeth")], set(), SNAP, TARGET_ROOT)
    assert [o for o in ops if o.kind == "RETAG"] == []


def test_retag_includes_only_fields_that_differ():
    # artist già giusto, title da correggere → il RETAG contiene solo title.
    f = make_audio_file(1, root_id=1, artist="Hermeth", title="vecchio", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Hermeth"), _accepted(1, "title", "Nuovo")],
                     set(), SNAP, TARGET_ROOT)
    retag = [o for o in ops if o.kind == "RETAG"][0]
    assert retag.before == {"title": "vecchio"} and retag.after == {"title": "Nuovo"}


def test_retag_after_matches_effective_when_two_fixes_same_field():
    f = make_audio_file(1, root_id=1, artist="X", title="T", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    fixes = [_accepted(1, "artist", "First"), _accepted(1, "artist", "Second")]
    ops = build_plan([f], fixes, set(), SNAP, TARGET_ROOT)
    retag = [o for o in ops if o.kind == "RETAG"][0]
    move = [o for o in ops if o.kind in ("RENAME", "MOVE")][0]
    # after must equal the value the rename actually used
    assert retag.after["artist"] in move.after["path"]


def test_no_op_retag_when_year_override_matches_int_year():
    # L'override "year" arriva come stringa ("to": "2020") ma AudioFile.year è int.
    # Se il valore è già quello giusto, non deve generare un RETAG fantasma.
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House", year=2020,
                        path="/lib/House/A/A - T.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "year", "2020")], set(), SNAP, TARGET_ROOT)
    assert [o for o in ops if o.kind == "RETAG"] == []


def test_real_year_change_still_produces_retag():
    # Regressione: un cambio di anno effettivo deve comunque generare RETAG.
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House", year=2019,
                        path="/lib/House/A/A - T.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "year", "2020")], set(), SNAP, TARGET_ROOT)
    retag = [o for o in ops if o.kind == "RETAG"]
    assert len(retag) == 1
    assert retag[0].after == {"year": "2020"}
