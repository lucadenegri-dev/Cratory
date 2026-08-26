"""La paginetta che incorpora il player YouTube.

Esiste per una ragione sola, e il primo test la nomina: dal 2025 YouTube
rifiuta gli embed che non arrivano con un `Referer` utilizzabile, e nel guscio
desktop la pagina sta su `tauri://localhost` — uno schema che un referrer
valido non lo produce. Servendo l'iframe dal backend, la richiesta a YouTube
parte da `http://127.0.0.1:8000`, che un referrer ce l'ha.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VIDEO = "dQw4w9WgXcQ"  # forma valida: 11 caratteri dell'alfabeto degli id


def test_la_pagina_incorpora_il_video_chiesto():
    r = client.get(f"/api/discovery/preview/youtube/{VIDEO}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert f"youtube-nocookie.com/embed/{VIDEO}" in r.text


def test_un_id_malformato_e_rifiutato():
    """L'id finisce dentro l'HTML: se non fosse validato, sarebbe il chiamante
    a scegliere cosa scriviamo nella pagina."""
    r = client.get("/api/discovery/preview/youtube/non-un-id")
    assert r.status_code == 400


def test_un_id_che_prova_a_iniettare_non_arriva_nella_pagina():
    """Il caso che il controllo esiste per fermare: virgolette e tag che
    chiuderebbero l'attributo `src` e aprirebbero altro."""
    veleno = '"><script>alert(1)</script>'
    r = client.get(f"/api/discovery/preview/youtube/{veleno}")
    assert r.status_code in (400, 404)
    assert "<script>alert(1)</script>" not in r.text


def test_id_di_lunghezza_sbagliata_rifiutato():
    """Undici caratteri esatti: dieci o dodici non sono id di YouTube, e
    accettarli vorrebbe dire incorporare una pagina che non esiste."""
    assert client.get("/api/discovery/preview/youtube/dQw4w9WgXc").status_code == 400
    assert client.get("/api/discovery/preview/youtube/dQw4w9WgXcQQ").status_code == 400
