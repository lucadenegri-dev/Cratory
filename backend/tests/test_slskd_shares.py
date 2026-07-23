"""Editor di `slskd.yml` per il flag "Condividi libreria".

slskd non permette di cambiare le share via API a runtime: si scrivono nello YAML.
L'editing deve essere non distruttivo (round-trip: preserva commenti/formato del
file con credenziali), idempotente, con backup e permessi preservati.
"""
import os
import stat
from pathlib import Path

import pytest

from app.services import slskd_shares

LIB = "/Users/tester/Music/Library"

CONFIG_WITH_COMMENT = """\
# slskd config di test — NON toccare i commenti
soulseek:
  username: tester      # credenziale finta
directories:
  downloads: /Users/tester/Music/Downloads
"""


def _write(tmp_path: Path, text: str = CONFIG_WITH_COMMENT, mode: int = 0o600) -> Path:
    p = tmp_path / "slskd.yml"
    p.write_text(text)
    p.chmod(mode)
    return p


def _shares(path: Path) -> list[str]:
    from ruamel.yaml import YAML
    data = YAML().load(path.read_text()) or {}
    return list((data.get("shares") or {}).get("directories") or [])


def test_enable_adds_directory(tmp_path):
    cfg = _write(tmp_path)
    present = slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    assert present is True
    assert LIB in _shares(cfg)


def test_enable_is_idempotent(tmp_path):
    cfg = _write(tmp_path)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    assert _shares(cfg).count(LIB) == 1


def test_disable_removes_directory(tmp_path):
    cfg = _write(tmp_path)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    present = slskd_shares.edit_shares_yaml(cfg, LIB, enabled=False)
    assert present is False
    assert LIB not in _shares(cfg)


def test_disable_when_absent_is_noop(tmp_path):
    cfg = _write(tmp_path)
    present = slskd_shares.edit_shares_yaml(cfg, LIB, enabled=False)
    assert present is False
    assert _shares(cfg) == []


def test_backup_created_with_original(tmp_path):
    cfg = _write(tmp_path)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    bak = cfg.with_suffix(cfg.suffix + ".bak")
    assert bak.exists()
    assert bak.read_text() == CONFIG_WITH_COMMENT


def test_roundtrip_preserves_comments(tmp_path):
    cfg = _write(tmp_path)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    text = cfg.read_text()
    assert "# slskd config di test" in text
    assert "# credenziale finta" in text


def test_chmod_600_preserved(tmp_path):
    cfg = _write(tmp_path, mode=0o600)
    slskd_shares.edit_shares_yaml(cfg, LIB, enabled=True)
    assert stat.S_IMODE(os.stat(cfg).st_mode) == 0o600


def test_set_library_share_daemon_down_does_not_raise(tmp_path, monkeypatch):
    cfg = _write(tmp_path)
    from app.core import runtime_settings as rs
    monkeypatch.setattr(rs, "slskd_config_path", lambda: str(cfg))
    monkeypatch.setattr(rs, "library_root", lambda: LIB)
    monkeypatch.setattr(rs, "slskd_url", lambda: "")  # slskd non configurato → niente client

    result = slskd_shares.set_library_share(True)
    assert result["applied_to_yaml"] is True
    assert result["rescan"] is False
    assert LIB in _shares(cfg)


def test_set_library_share_enable_requires_library(tmp_path, monkeypatch):
    cfg = _write(tmp_path)
    from app.core import runtime_settings as rs
    monkeypatch.setattr(rs, "slskd_config_path", lambda: str(cfg))
    monkeypatch.setattr(rs, "library_root", lambda: "")
    with pytest.raises(slskd_shares.ShareError):
        slskd_shares.set_library_share(True)


def test_set_library_share_missing_config_raises(tmp_path, monkeypatch):
    from app.core import runtime_settings as rs
    monkeypatch.setattr(rs, "slskd_config_path", lambda: str(tmp_path / "nope.yml"))
    monkeypatch.setattr(rs, "library_root", lambda: LIB)
    with pytest.raises(slskd_shares.ShareError):
        slskd_shares.set_library_share(True)
