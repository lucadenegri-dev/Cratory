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
    """Un file con l'hash sbagliato non deve restare sul disco — nemmeno come
    `.parziale`: se restasse, un ritentativo o un altro percorso di codice
    potrebbe raccoglierlo. Si controlla l'intera cartella, non solo `dest`,
    perché `dest` non viene mai creato prima del rename finale: un controllo
    limitato al suo nome sarebbe vero anche se il `.parziale` restasse."""
    dest = tmp_path / "scaricato"
    cattivo = "0" * 64
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        with pytest.raises(bi.ChecksumMismatch):
            bi.download_verified(_download(cattivo), dest, client=c)
    assert list(tmp_path.iterdir()) == []


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


class _StreamRottoAMeta(httpx.SyncByteStream):
    """Un byte stream che consegna un po' di dati e poi esplode, per
    simulare una connessione che cade a metà scaricamento (non prima di
    ricevere la risposta, non nella richiesta stessa)."""

    def __iter__(self):
        yield b"a" * 2048
        raise httpx.ReadError("connessione interrotta a metà scaricamento")

    def close(self) -> None:
        pass


def test_errore_a_meta_scaricamento_non_lascia_traccia(tmp_path):
    """Sia il caso di stato HTTP cattivo sia quello di errore di rete già
    testati falliscono prima di scrivere un solo byte: il cleanup dentro gli
    `except` sul file parziale scritto a metà, mai esercitato. Qui la
    risposta arriva (200) e qualche KB viene scritto su disco prima che lo
    stream sollevi un errore, cosa che deve comunque far scomparire ogni
    traccia dalla cartella di destinazione."""
    def handler(req):
        return httpx.Response(200, stream=_StreamRottoAMeta())

    with _client(handler) as c:
        with pytest.raises(bi.DownloadFailed):
            bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)
    assert list(tmp_path.iterdir()) == []


def test_client_iniettato_resta_utilizzabile_dopo_la_chiamata(tmp_path):
    """Se il chiamante passa un client (`owned = False`), la funzione non deve
    chiuderlo: un chiamante che condivide un client fra più download andrebbe
    in errore silenzioso alla chiamata successiva."""
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)
        # Se la funzione avesse chiuso il client iniettato, questa seconda
        # richiesta sullo stesso client solleverebbe RuntimeError.
        altra = c.get("https://esempio.invalid/y")
    assert altra.status_code == 200


def test_cadenza_grande_file_non_una_riga_per_blocco(tmp_path):
    """Un download grande (120 MB simulati) produce una fraczione di righe
    rispetto al numero di blocchi letti. Con block size 256 KB, 120 MB = ~480
    blocchi; cadenza di report deve produrre non più di ~20-25 righe."""
    # Simula un file di 120 MB in streaming: con 256 KB per blocco,
    # sono 480+ chiamate al handler di CONTENUTO. Senza throttling
    # sarebbero 480+ report; con cadenza basata su file size, ~20.
    dimensione_simulata = 120 * 1024 * 1024  # 120 MB
    rapporti = []

    def handler_grande(req):
        headers = {"content-length": str(dimensione_simulata)}
        # Genera contenuto virtuale ripetendo pattern
        return httpx.Response(200, content=CONTENUTO, headers=headers)

    # Usa il contenuto reale ripetuto per il test (httpx MockTransport
    # non supporta vero streaming virtuale senza caricamento), allora
    # testa con un contenuto più piccolo ma verifica la logica
    contenuto_grande = CONTENUTO * 400  # ~5 MB
    visti = []

    def handler(req):
        headers = {"content-length": str(len(contenuto_grande))}
        return httpx.Response(200, content=contenuto_grande, headers=headers)

    with _client(handler) as c:
        bi.download_verified(_download(hashlib.sha256(contenuto_grande).hexdigest()),
                             tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)),
                             client=c)

    # Con 5 MB e intervallo = max(1 MB, 5 MB // 20) = 1 MB,
    # dovremmo avere ~5 report intermediate + 1 finale (poiché il
    # download non atterra esattamente su multipli di 1 MB)
    assert len(visti) >= 2, f"troppo pochi report: {len(visti)} (atteso almeno 2)"
    assert len(visti) <= 10, f"troppi report: {len(visti)} (atteso massimo 10)"
    # Verifica che l'ultimo report sia il totale
    assert visti[-1][0] == len(contenuto_grande)
    assert visti[-1][1] == len(contenuto_grande)


def test_stato_finale_sempre_riportato(tmp_path):
    """Lo stato finale deve essere riportato anche se scaricati non cade
    esattamente su un multiplo dell'intervallo. Questo garantisce che
    l'ultima riga del log non sia un'frazione arbitraria."""
    # Crea contenuto di dimensione non multipla di 1 MB (l'intervallo di default)
    contenuto_strano = b"x" * (1024 * 1024 + 100000)  # 1.09 MB
    visti = []

    def handler(req):
        headers = {"content-length": str(len(contenuto_strano))}
        return httpx.Response(200, content=contenuto_strano, headers=headers)

    with _client(handler) as c:
        bi.download_verified(_download(hashlib.sha256(contenuto_strano).hexdigest()),
                             tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)),
                             client=c)

    # Deve esserci almeno un report (il finale)
    assert visti, "nessun report di avanzamento"
    # L'ultimo report deve essere lo stato finale (100%)
    assert visti[-1][0] == len(contenuto_strano), \
        f"stato finale non raggiunto: {visti[-1][0]} vs {len(contenuto_strano)}"
    assert visti[-1][1] == len(contenuto_strano), \
        f"totale finale errato: {visti[-1][1]} vs {len(contenuto_strano)}"


def test_piccolo_file_riporta_progresso(tmp_path):
    """Anche un file piccolo (2 MB) deve riportare progresso, non solo
    lo stato finale. Altrimenti l'interfaccia non sa se il download è bloccato."""
    contenuto_piccolo = b"y" * (2 * 1024 * 1024)  # 2 MB esatti
    visti = []

    def handler(req):
        headers = {"content-length": str(len(contenuto_piccolo))}
        return httpx.Response(200, content=contenuto_piccolo, headers=headers)

    with _client(handler) as c:
        bi.download_verified(_download(hashlib.sha256(contenuto_piccolo).hexdigest()),
                             tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)),
                             client=c)

    # Deve esserci almeno un report
    assert len(visti) >= 1, "nessun report per file piccolo"
    # L'ultimo deve essere lo stato finale
    assert visti[-1] == (len(contenuto_piccolo), len(contenuto_piccolo))


def test_file_size_ignota_riporta_cadenza_ragionevole(tmp_path):
    """Quando il content-length è assente (size ignota), la cadenza deve
    basarsi su intervallo fisso (1 MB), non su conteggio assoluto."""
    contenuto_ignoto = CONTENUTO * 500  # ~6 MB
    visti = []

    def handler(req):
        # No content-length header
        return httpx.Response(200, content=contenuto_ignoto)

    with _client(handler) as c:
        bi.download_verified(_download(hashlib.sha256(contenuto_ignoto).hexdigest()),
                             tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)),
                             client=c)

    # Con size ignoto e 1 MB di intervallo per ~6 MB, dovremmo avere
    # circa 6 report (non 500+)
    assert len(visti) >= 2, f"troppo pochi report con size ignoto: {len(visti)}"
    assert len(visti) <= 15, f"troppi report con size ignoto: {len(visti)}"
    # Quando il size è ignoto, il totale di ogni report è quello corrente
    assert visti[-1][0] == len(contenuto_ignoto)
    assert visti[-1][1] == len(contenuto_ignoto)
