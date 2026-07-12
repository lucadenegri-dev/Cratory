"""Worker CLI: esegue l'analisi Essentia di un singolo file in un processo separato.

Uso: ``python -m app.integrations.essentia_worker <path>`` -> stampa su stdout un
JSON ``{"bpm": float|null, "camelot": str|null}`` ed esce con codice 0; su errore
(file illeggibile, Essentia assente) l'eccezione propaga, il traceback va su stderr
e il codice d'uscita e' != 0.

Perche' un processo separato: Essentia e' C++ e trattiene il GIL per secondi su una
traccia reale. Eseguirla nel thread del job (stesso processo del web server
single-worker) congelerebbe tutte le altre richieste finche' l'analisi non finisce.
Il subprocess isola quel lavoro CPU-bound; il chiamante resta in attesa I/O e
rilascia il GIL (stesso pattern di ffmpeg per l'indicizzazione). Vedi
essentia_engine.analyze_subprocess."""

import json
import sys

from app.integrations.essentia_engine import analyze


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.integrations.essentia_worker <path>", file=sys.stderr)
        return 2
    res = analyze(argv[1])  # propaga su file illeggibile -> rc != 0
    json.dump({"bpm": res.bpm, "camelot": res.camelot}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
