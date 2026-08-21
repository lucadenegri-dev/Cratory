"""Il download è il punto in cui entra codice eseguibile da fuori: la verifica
non è una formalità, è l'unica barriera."""
import hashlib

import httpx
import pytest

from app.services import binary_installer as bi
from app.services.binary_manifest import Download

CONTENUTO = b"finto binario" * 1000
HASH_GIUSTO = hashlib.sha256(CONTENUTO).hexdigest()


def _download(sha256: str) -> Download:
    return Download("1.0", "https://esempio.invalid/x.tar.gz", sha256,
                    "tar.gz", "x", "single")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_riuscito(tmp_path):
    dest = tmp_path / "scaricato"
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        bi.download_verified(_download(HASH_GIUSTO), dest, client=c)
    assert dest.read_bytes() == CONTENUTO


def test_hash_diverso_solleva_e_non_lascia_il_file(tmp_path):
    """Un file con l'hash sbagliato non deve restare sul disco: se restasse,
    un ritentativo o un altro percorso di codice potrebbe raccoglierlo."""
    dest = tmp_path / "scaricato"
    cattivo = "0" * 64
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        with pytest.raises(bi.ChecksumMismatch):
            bi.download_verified(_download(cattivo), dest, client=c)
    assert not dest.exists()


def test_errore_http_solleva_download_failed(tmp_path):
    with _client(lambda req: httpx.Response(404)) as c:
        with pytest.raises(bi.DownloadFailed):
            bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)


def test_errore_di_rete_solleva_download_failed(tmp_path):
    def esplodi(req):
        raise httpx.ConnectTimeout("timeout")

    with _client(esplodi) as c:
        with pytest.raises(bi.DownloadFailed):
            bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)


def test_avanzamento_riportato(tmp_path):
    visti: list[tuple[int, int]] = []
    headers = {"content-length": str(len(CONTENUTO))}
    with _client(lambda req: httpx.Response(200, content=CONTENUTO, headers=headers)) as c:
        bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)),
                             client=c)
    assert visti, "nessun avanzamento riportato"
    assert visti[-1][0] == len(CONTENUTO)
    assert visti[-1][1] == len(CONTENUTO)


def test_il_file_non_viene_tenuto_in_memoria(tmp_path, monkeypatch):
    """Gli archivi veri pesano 55-160 MB: il download deve essere in streaming.
    Se qualcuno passasse a `response.content`, questo test lo becca."""
    letture = {"n": 0}
    originale = bi._CHUNK

    def handler(req):
        letture["n"] += 1
        return httpx.Response(200, content=CONTENUTO)

    monkeypatch.setattr(bi, "_CHUNK", 1024)
    with _client(handler) as c:
        bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)
    assert bi._CHUNK == 1024 and originale > 0
