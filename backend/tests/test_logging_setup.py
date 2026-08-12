"""setup_logging() rimuove gli handler precedenti dal root logger ma deve anche
chiuderli: altrimenti il RotatingFileHandler resta con il file aperto e, quando
il garbage collector lo raccoglie, Python emette un ResourceWarning "unclosed
file". setup_logging() viene chiamata dal lifespan di FastAPI, quindi ogni
TestClient(app) in un test ne perde uno (27 errori misurati in tests/organize,
dove i warning sono trattati come errori)."""
import logging

from app.core.config import setup_logging


def test_setup_logging_closes_previous_file_handler():
    """Due chiamate consecutive: l'handler file della prima chiamata deve
    risultare chiuso (stream sottostante chiuso) dopo la seconda."""
    setup_logging()
    root = logging.getLogger()
    first_file_handlers = [
        h for h in root.handlers if isinstance(h, logging.FileHandler)
    ]
    assert first_file_handlers, "setup_logging() deve installare un FileHandler"
    first_file_handler = first_file_handlers[0]

    setup_logging()

    # Un handler chiuso ha lo stream sottostante chiuso; RotatingFileHandler
    # (come FileHandler) espone lo stream su .stream e close() lo chiude.
    assert first_file_handler.stream is None or first_file_handler.stream.closed, (
        "l'handler file rimosso dalla prima chiamata non e' stato chiuso: "
        "il file descriptor resta aperto (ResourceWarning: unclosed file)"
    )
