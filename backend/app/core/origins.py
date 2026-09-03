"""Le origini che questa installazione riconosce come proprie.

Vive fuori da `main.py` perche' non serve piu' solo al CORS: il callback OAuth
di Spotify valida contro questa stessa lista la destinazione di ritorno che la
pagina gli chiede (`routers/spotify.py`), e un router non puo' importare
`app.main` — sarebbe circolare, e' `main` a importare i router.
"""

# L'origin che il webview di Tauri presenta su macOS. Non e' configurabile:
# se cambiasse, l'app desktop smetterebbe di funzionare e il posto in cui
# accorgersene e' qui, non il .env di chi installa.
WEBVIEW_ORIGIN = "tauri://localhost"


def origini_ammesse(raw: str) -> list[str]:
    """Le origini che il CORS accetta, dalla stringa separata da virgole.

    Funzione e non espressione in linea perche' i test la chiamano invece di
    riscriverla: una copia della logica nel test si disallinea al primo
    cambiamento, ed e' gia' successo.
    """
    return sorted({o.strip() for o in raw.split(",") if o.strip()} | {WEBVIEW_ORIGIN})
