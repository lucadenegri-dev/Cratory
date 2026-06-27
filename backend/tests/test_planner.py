from app.models import Issue
from app.services.planner import build_plan, render_destination, effective_tags
from tests.conftest import make_audio_file

SNAP = {"naming_template": "{artist} - {title}", "folder_template": "{genre}/{artist}"}
TARGETS = {1: "/lib"}


def _accepted(file_id, field, to=None, action="retag"):
    fix = {"field": field, "action": action}
    if to is not None:
        fix["to"] = to
    return Issue(file_id=file_id, type="x", field=field, severity="warning",
                 detail="", suggested_fix_json=fix, status="accepted")


def test_retag_aggregates_per_file():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="bel titolo", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGETS)
    retag = [o for o in ops if o.kind == "RETAG"]
    assert len(retag) == 1
    assert retag[0].before == {"artist": "PINCO"} and retag[0].after == {"artist": "Pinco"}


def test_effective_tags_used_in_rename():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="T", genre="House",
                        path="/lib/old.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGETS)
    move = [o for o in ops if o.kind in ("RENAME", "MOVE")][0]
    assert move.after["path"] == "/lib/House/Pinco/Pinco - T.mp3"  # usa l'artist corretto


def test_rename_vs_move():
    # già in /lib/House/A, cambia solo il nome → RENAME
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/House/A/vecchio.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops[0].kind == "RENAME" and ops[0].after["path"] == "/lib/House/A/A - T.mp3"


def test_move_to_different_folder():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops[0].kind == "MOVE"


def test_removed_file_only_delete():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], {1}, SNAP, TARGETS)
    assert [o.kind for o in ops] == ["DELETE"]
    assert ops[0].before == {"path": "/lib/varie/x.mp3"}


def test_sanitize_path_chars():
    f = make_audio_file(1, root_id=1, artist="AC/DC", title="T", genre="Rock",
                        path="/lib/x.mp3", ext="mp3")
    dest, miss = render_destination(f, effective_tags(f, []), SNAP, TARGETS)
    assert "AC_DC" in dest and ".." not in dest


def test_missing_field_no_op():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops == []  # genre mancante per {genre}/... → nessuna rinomina


def test_order_and_determinism():
    keep = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                           path="/lib/varie/a.mp3", ext="mp3")
    rem = make_audio_file(2, root_id=1, artist="B", title="U", genre="House",
                          path="/lib/varie/b.mp3", ext="mp3")
    ops = build_plan([keep, rem], [_accepted(1, "artist", "A")], {2}, SNAP, TARGETS)
    assert [o.kind for o in ops] == ["RETAG", "MOVE", "DELETE"]
    assert build_plan([rem, keep], [_accepted(1, "artist", "A")], {2}, SNAP, TARGETS) == ops
