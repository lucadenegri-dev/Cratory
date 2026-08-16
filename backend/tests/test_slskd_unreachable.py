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
    status code (dato dal test) e, se serve, il corpo della risposta."""

    def __init__(self, status, text=""):
        self.status = status
        self.text = text

    def post(self, url, json=None):
        return _Resp(self.status, self.text)


def _enqueue_and_capture(http: object) -> SlskdError:
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


@pytest.mark.parametrize("status", [404, 422])
def test_gli_altri_4xx_restano_un_fallimento_della_richiesta(status):
    """I 4xx non elencati nella tabella riguardano la singola richiesta/traccia,
    non il daemon: l'item deve concludersi `failed`, non tornare in coda."""
    exc = _enqueue_and_capture(_StatusHttp(status))
    assert exc.status_code == status
    assert slskd_unreachable(exc) is False


@pytest.mark.parametrize("corpo", [
    "must be connected (currently: Disconnected)",
    "The server must be connected to perform this action.",
    "Currently: Disconnected",
])
def test_il_409_da_rete_soulseek_scollegata_e_infrastruttura(corpo):
    """Il 409 che slskd manda a daemon vivo ma non collegato alla rete Soulseek
    e' la condizione piu' frequente dopo un riavvio o un blip di rete, e non ha
    niente a che vedere con la traccia. Trattarlo come colpa della traccia,
    con 300 item in coda, li marca tutti `failed` e scrive l'esito su 300
    tracce."""
    exc = _enqueue_and_capture(_StatusHttp(409, corpo))
    assert exc.status_code == 409
    assert slskd_unreachable(exc) is True


def test_un_409_che_non_parla_di_connessione_resta_della_richiesta():
    """La lettura del testo non deve diventare "ogni 409 e' infrastruttura":
    un conflitto vero (es. lo stesso file gia' in coda) riguarda la richiesta."""
    exc = _enqueue_and_capture(_StatusHttp(409, "file already queued"))
    assert slskd_unreachable(exc) is False


@pytest.mark.parametrize("corpo", [
    "User bob is disconnected",
    "Peer soulseeker99 is not connected",
])
def test_un_peer_scollegato_e_colpa_del_candidato_non_del_daemon(corpo):
    """Un peer offline non e' infrastruttura: e' il candidato che non va.

    Sbagliare in questo verso non ha rete di sicurezza. Un item classificato
    "infrastruttura" torna in coda con `attempts` DECREMENTATO, quindi non
    fallisce mai; il dispatcher mette in pausa il pool, il riaggancio lo
    ripesca, e si ricomincia — all'infinito. Il verso opposto (un motivo
    d'infrastruttura non riconosciuto) e' invece coperto dall'interruttore per
    fallimenti consecutivi del dispatcher, che conta solo i fallimenti veri.
    Per questo i frammenti riconosciuti devono parlare del SERVER e di nient'altro.
    """
    exc = _enqueue_and_capture(_StatusHttp(409, corpo))
    assert slskd_unreachable(exc) is False
