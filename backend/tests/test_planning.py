from app.models import ScanRoot
from app.services import planning


def test_get_settings_seeds_defaults(db):
    s = planning.get_settings(db)
    assert s.naming_template == "{artist} - {title}"
    assert s.folder_template == "{genre}/{artist}"


def test_update_settings(db):
    planning.get_settings(db)
    s = planning.update_settings(db, folder_template="{genre}")
    assert s.folder_template == "{genre}" and s.naming_template == "{artist} - {title}"


def test_set_root_target_and_map(db):
    root = ScanRoot(id=1, path="/lib")
    db.add(root)
    db.commit()
    planning.set_root_target(db, 1, "/lib/Library")
    assert planning.root_targets(db) == {1: "/lib/Library"}
    planning.set_root_target(db, 1, None)  # in-place → la radice stessa
    assert planning.root_targets(db) == {1: "/lib"}
