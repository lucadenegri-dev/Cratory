from app.services.conflict import check, disk_occupied
from app.services.planner import PlanOpComputed, build_plan
from tests.conftest import make_audio_file

SNAP = {"naming_template": "{artist} - {title}", "folder_template": "{genre}/{artist}"}
TARGETS = {1: "/lib"}


def test_clean_plan_no_conflicts():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert check(ops, {1: f}, [], set(), SNAP, TARGETS) == []


def test_collision_two_same_dest():
    a = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/1.mp3", ext="mp3")
    b = make_audio_file(2, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/2.mp3", ext="mp3")  # stesso artist+title+genre → stessa dest
    ops = build_plan([a, b], [], set(), SNAP, TARGETS)
    conflicts = check(ops, {1: a, 2: b}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "collision" for c in conflicts)


def test_missing_template_data():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    conflicts = check([], {1: f}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "missing_template_data" and c.file_id == 1 for c in conflicts)


def test_outside_root():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    bad_op = PlanOpComputed("MOVE", 1, {"path": "/lib/x.mp3"}, {"path": "/altrove/A - T.mp3"})
    conflicts = check([bad_op], {1: f}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "outside_root" for c in conflicts)


def test_removed_file_not_missing_data():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    # rimosso: niente rinomina → niente conflitto missing_data
    assert check([], {1: f}, [], {1}, SNAP, TARGETS) == []


def test_disk_occupied_detects_untracked_dest(tmp_path):
    # La dest esiste su disco ma non è nel DB (es. Library organizzata non scansionata).
    src = tmp_path / "src.mp3"; src.write_text("a")
    dest = tmp_path / "House" / "A - T.mp3"
    dest.parent.mkdir(); dest.write_text("b")
    op = PlanOpComputed("MOVE", 1, {"path": str(src)}, {"path": str(dest)})
    assert disk_occupied([op]) == {str(dest)}


def test_disk_occupied_ignores_case_only_rename(tmp_path):
    # dest == src a meno del case (samefile su APFS): non è un'occupazione.
    src = tmp_path / "a - t.mp3"; src.write_text("a")
    dest = tmp_path / "A - T.mp3"
    op = PlanOpComputed("RENAME", 1, {"path": str(src)}, {"path": str(dest)})
    assert disk_occupied([op]) == set()


def test_disk_occupied_ignores_delete_target(tmp_path):
    # Lo slot è occupato da un file che il piano stesso elimina (delete-prima-di-move).
    src = tmp_path / "src.mp3"; src.write_text("a")
    dest = tmp_path / "A - T.mp3"; dest.write_text("b")
    mv = PlanOpComputed("MOVE", 1, {"path": str(src)}, {"path": str(dest)})
    rm = PlanOpComputed("DELETE", 2, {"path": str(dest)}, {})
    assert disk_occupied([mv, rm]) == set()


def test_disk_occupied_ignores_free_dest(tmp_path):
    src = tmp_path / "src.mp3"; src.write_text("a")
    op = PlanOpComputed("MOVE", 1, {"path": str(src)}, {"path": str(tmp_path / "libera.mp3")})
    assert disk_occupied([op]) == set()


def test_check_flags_disk_occupied_dest():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    dest = ops[0].after["path"]
    conflicts = check(ops, {1: f}, [], set(), SNAP, TARGETS, disk_occupied={dest})
    assert any(c.kind == "collision" and "su disco" in c.detail for c in conflicts)


def test_move_into_removed_file_slot_not_collision():
    keeper = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                             path="/lib/varie/k.mp3", ext="mp3")
    dup = make_audio_file(2, root_id=1, artist="A", title="T", genre="House",
                          path="/lib/House/A/A - T.mp3", ext="mp3")  # occupa lo slot destinazione del keeper
    ops = build_plan([keeper, dup], [], {2}, SNAP, TARGETS)  # dup rimosso
    conflicts = check(ops, {1: keeper, 2: dup}, [], {2}, SNAP, TARGETS)
    assert not any(c.kind == "collision" for c in conflicts)
