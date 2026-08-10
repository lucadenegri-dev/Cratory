from types import SimpleNamespace

from app.organize.services.planner import build_plan


def _file(fid, has_cover=False):
    return SimpleNamespace(
        id=fid, root_id=1, path=f"/music/{fid}.flac", ext="flac",
        artist="A", title="T", album=None, album_artist=None, genre="House",
        year=None, label=None, track_no=None, comment=None, has_cover=has_cover)


def _cover_issue(fid, status="accepted"):
    return SimpleNamespace(
        file_id=fid, type="missing_cover", field="cover", status=status,
        suggested_fix_json={"field": "cover", "source": "caa", "confidence": "high",
                            "full_url": "http://f.jpg", "thumb_ref": f"cover_cache/{fid}.jpg"})


_SNAP = {"naming_template": "{artist} - {title}", "folder_template": ""}


def test_cover_op_emitted_for_accepted_missing_cover():
    files = [_file(1, has_cover=False)]
    ops = build_plan(files, [_cover_issue(1)], set(), _SNAP, {1: "/music"})
    cover = [o for o in ops if o.kind == "COVER"]
    assert len(cover) == 1
    assert cover[0].file_id == 1
    assert cover[0].after["full_url"] == "http://f.jpg"
    assert cover[0].after["source"] == "caa"


def test_no_cover_op_when_file_already_has_cover():
    files = [_file(1, has_cover=True)]
    ops = build_plan(files, [_cover_issue(1)], set(), _SNAP, {1: "/music"})
    assert [o for o in ops if o.kind == "COVER"] == []


def test_no_cover_op_when_file_in_removals():
    files = [_file(1, has_cover=False)]
    ops = build_plan(files, [_cover_issue(1)], {1}, _SNAP, {1: "/music"})
    assert [o for o in ops if o.kind == "COVER"] == []
