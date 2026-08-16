"""`slskd_unreachable`: la tabella di classificazione infrastruttura/traccia (rilievo).

Prima di questa correzione lo status HTTP non sopravviveva a `raise_for_status`
(costruiva l'eccezione dal solo status code, senza causa httpx): un daemon vivo
che rispondeva 401 (chiave API sbagliata o ruotata) o 5xx finiva comunque nel
ramo "colpa della traccia", proprio come un 409 — bruciando la coda intera se
il riaggancio periodico ripescava un daemon in quello stato. Questi test
passano dal client vero (`SlskdClient`) cosi' esercitano l'intera catena:
`raise_for_status` (che ora attacca `.status_code` all'eccezione) ->
`slskd_unreachable` (che lo legge).
"""

import httpx
import pytest

from app.integrations.slskd import SlskdClient, SlskdError, SlskdFile, slskd_unreachable


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text
        self.content = b""

    def json(self):
        return {}


class _RefusedHttp:
    """Connessione rifiutata: il verbo alza direttamente l'errore di trasporto
    httpx, prima ancora di ricevere una risposta — nessuno status code."""

    def post(self, url, json=None):
        raise httpx.ConnectError("[Errno 61] Connection refused")


class _StatusHttp:
    """Il daemon e' vivo e risponde: nessun errore di trasporto, solo uno
    status code (dato dal test)."""

    def __init__(self, status):
        self.status = status

    def post(self, url, json=None):
        return _Resp(self.status)


def _enqueue_and_capture(http) -> SlskdError:
    client = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    file = SlskdFile(username="bob", filename="x.flac", size=1, bitrate=None,
                     length=None, has_free_slot=True, queue_length=None)
    with pytest.raises(SlskdError) as exc_info:
        client.enqueue_download(file)
    return exc_info.value


def test_connessione_rifiutata_e_irraggiungibile():
    exc = _enqueue_and_capture(_RefusedHttp())
    assert isinstance(exc.__cause__, httpx.TransportError)
    assert slskd_unreachable(exc) is True


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_401_403_e_5xx_di_un_daemon_vivo_sono_irraggiungibili(status):
    """Un daemon vivo che risponde male (chiave ruotata, o un 5xx qualsiasi)
    e' infrastruttura tanto quanto una connessione rifiutata: la coda deve
    mettersi in pausa, non bruciare l'item."""
    exc = _enqueue_and_capture(_StatusHttp(status))
    assert exc.__cause__ is None                 # nessuna causa httpx: e' status-based
    assert exc.status_code == status
    assert slskd_unreachable(exc) is True


@pytest.mark.parametrize("status", [409, 404, 422])
def test_409_e_altri_4xx_restano_un_fallimento_della_richiesta(status):
    """Il 409 "must be connected" (e altri 4xx non elencati nella tabella)
    riguardano la singola richiesta/traccia, non il daemon: l'item deve
    concludersi `failed`, non tornare in coda all'infinito."""
    exc = _enqueue_and_capture(_StatusHttp(status))
    assert exc.status_code == status
    assert slskd_unreachable(exc) is False
