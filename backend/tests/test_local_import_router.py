"""Endpoint import locale: browse, avvio (validazione), stato. Chiamate dirette al router."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import playlists
from app.schemas import LocalFolderImportRequest
from app.services import local_import_job


def test_browse_ritorna_sottocartelle(tmp_path, monkeypatch):
    (tmp_path / "house").mkdir()
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    res = playlists.browse_local_folder(path=str(tmp_path))
    assert [d.name for d in res.dirs] == ["house"]
    assert res.current_path == str(tmp_path.resolve())


def test_browse_fuori_root_400(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: root)
    with pytest.raises(HTTPException) as ei:
        playlists.browse_local_folder(path=str(tmp_path))
    assert ei.value.status_code == 400


def test_import_local_path_inesistente_400(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    req = LocalFolderImportRequest(path=str(tmp_path / "nope"))
    with pytest.raises(HTTPException) as ei:
        playlists.import_local_folder_endpoint(req)
    assert ei.value.status_code == 400


def test_import_local_avvia_job(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    called = {}
    monkeypatch.setattr(local_import_job, "start_job",
                        lambda *, path, name: called.update(path=path, name=name) or local_import_job.job_state())
    monkeypatch.setattr(local_import_job, "is_running", lambda: False)
    req = LocalFolderImportRequest(path=str(tmp_path), name="Crate")
    res = playlists.import_local_folder_endpoint(req)
    assert called["path"] == str(tmp_path)
    assert res.status in {"idle", "running", "done", "error"}


def test_import_local_gia_in_corso_409(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    monkeypatch.setattr(local_import_job, "is_running", lambda: True)
    req = LocalFolderImportRequest(path=str(tmp_path))
    with pytest.raises(HTTPException) as ei:
        playlists.import_local_folder_endpoint(req)
    assert ei.value.status_code == 409


def test_status_ritorna_stato(monkeypatch):
    monkeypatch.setattr(local_import_job, "job_state",
                        lambda: {"status": "done", "processed": 1, "total": 1, "created": 1,
                                 "updated": 0, "failed": 0, "playlist_id": 5, "errors": [],
                                 "error": None})
    res = playlists.local_import_status()
    assert res.status == "done"
    assert res.playlist_id == 5
