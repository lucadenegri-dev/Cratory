"""Cosa scaricare per ogni binario esterno e per ogni piattaforma.

Dati puri, separati dal registry del probe di proposito: questo file cambia
con la cadenza dei bump di versione, il registry descrive comportamento.

Versione e SHA256 sono FISSATI. Stiamo scaricando ed eseguendo binari: l'hash
pinnato è ciò che impedisce a una release manomessa a monte di entrare. Il
digest che GitHub espone nella sua API serve a compilare questo file, non a
fidarsene al momento del download — verrebbe dalla stessa fonte del file.

Per aggiornare un pin: `gh api repos/<owner>/<repo>/releases/tags/<tag>
--jq '.assets[] | "\\(.name) \\(.digest)"'`, poi si aggiorna qui versione,
URL e hash insieme.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Download:
    version: str
    url: str
    sha256: str
    archive: Literal["tar.gz", "tar.xz", "zip"]
    # Basename dell'eseguibile: lo si cerca dentro l'archivio invece di
    # pinnarne il percorso interno, che cambia a ogni build (le release di
    # ffmpeg lo annidano sotto una cartella che porta il numero di build).
    member: str
    # "single": si estrae solo `member` dentro bin/.
    # "bundle": si estrae tutto in bin/<key>/ perché l'eseguibile non è
    # autosufficiente (slskd porta con sé il runtime .NET).
    layout: Literal["single", "bundle"]
    # Flag con cui si invoca il binario per il controllo "parte davvero":
    # non è universale, ogni progetto sceglie il proprio (fpcalc e ffmpeg
    # accettano `-version`, slskd solo `-v`/`--version`). Stesso campo che
    # `system_probe.Component.version_flag` usa per il probe a runtime. Il
    # default copre la maggioranza (fpcalc/ffmpeg): ogni voce del manifesto
    # lo passa comunque esplicito, il default esiste solo per non costringere
    # i test di extract/download — che non hanno niente a che fare con
    # l'esecuzione del binario — a conoscere questo campo.
    version_flag: str = "-version"


_ARCH_ALIASES = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}


def platform_tag() -> str:
    """Chiave del manifesto per la macchina corrente, es. `darwin-arm64`."""
    arch = platform.machine().lower()
    return f"{sys.platform}-{_ARCH_ALIASES.get(arch, arch)}"


_FPCALC = "https://github.com/acoustid/chromaprint/releases/download/v1.6.1"
_SLSKD = "https://github.com/slskd/slskd/releases/download/0.26.0"
_FFMPEG = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
           "autobuild-2026-08-19-19-21")

MANIFEST: dict[str, dict[str, Download]] = {
    # Chromaprint pubblica binari ufficiali per ogni piattaforma: è il caso
    # pulito. La build universale copre entrambe le architetture Apple.
    "fpcalc": {
        "darwin-arm64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-macos-universal.tar.gz",
            "240aeb5a8c8205af458e3625cb7487b826b711a999e491ef00111f3cebd76f00",
            "tar.gz", "fpcalc", "single", "-version"),
        "darwin-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-macos-universal.tar.gz",
            "240aeb5a8c8205af458e3625cb7487b826b711a999e491ef00111f3cebd76f00",
            "tar.gz", "fpcalc", "single", "-version"),
        "linux-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz",
            "fc16cd37a70168040bc9ceb45f1d4d1216f5a75bc4c9cf8564bea70ac6a45733",
            "tar.gz", "fpcalc", "single", "-version"),
        "linux-arm64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-linux-arm64.tar.gz",
            "7eaf5d655c4aa172ab28e3c870b8bb61dd2c327ac94de145676f88842cf6215a",
            "tar.gz", "fpcalc", "single", "-version"),
        "win32-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-windows-x86_64.zip",
            "735d6182b38e9f364b84ce6f4ccd682c75e2851de89735711d6b762d12b92a4e",
            "zip", "fpcalc.exe", "single", "-version"),
    },
    # ffmpeg: NESSUNA voce macOS, per decisione esplicita della spec — BtbN non
    # produce asset macOS e non esiste altrove una build arm64 nativa con
    # checksum pubblicato. Su macOS si ricade sul comando manuale.
    "ffmpeg": {
        "linux-x86_64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-linux64-gpl.tar.xz",
            "c3df9379d32a16f6923681411c97880ee8d45b0bae03a55a6fc8262f2f653ba6",
            "tar.xz", "ffmpeg", "bundle", "-version"),
        "linux-arm64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-linuxarm64-gpl.tar.xz",
            "e184dbde7d57d8f1ffa616795d9c4f6f368b211bc9e6fd86b60fea511a21f430",
            "tar.xz", "ffmpeg", "bundle", "-version"),
        "win32-x86_64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-win64-gpl.zip",
            "fe5a8f090b9fbc77d5e64c7d8b404b8837e05a09663ed9768ba19284cf929b20",
            "zip", "ffmpeg.exe", "bundle", "-version"),
    },
    # slskd accetta solo `-v`/`--version`: `-version` (un solo trattino, quello
    # che va bene per fpcalc e ffmpeg) non è un'opzione riconosciuta e la
    # prova di esecuzione fallirebbe sempre. Layout `bundle` come ffmpeg (il
    # runtime .NET che porta con sé, non un eseguibile autosufficiente), ma
    # col flag sbagliato per gli altri due.
    "slskd": {
        "darwin-arm64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-osx-arm64.zip",
            "53bd82e26224908abb30780f3e3a3ee58788d17379354b3138c85c6fe02cd5a0",
            "zip", "slskd", "bundle", "--version"),
        "darwin-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-osx-x64.zip",
            "3d624c53de73229caa090c395ee5eada9c7f54d59fd3a0e79a2597e8b467b448",
            "zip", "slskd", "bundle", "--version"),
        "linux-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-linux-x64.zip",
            "9c19c04767ef036a47716404d097433e23fbdb41b339e0e8cbc2329c98b22583",
            "zip", "slskd", "bundle", "--version"),
        "linux-arm64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-linux-arm64.zip",
            "57d4b9dbb0ad34aa6e6aaaf79b0bf3347dec5efcb48ad2b12f9ed4ece42787aa",
            "zip", "slskd", "bundle", "--version"),
        "win32-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-win-x64.zip",
            "942299d8c97da6cc1f6cd82dcd4a3662b97b82fbd1742df4bec165b79357268a",
            "zip", "slskd.exe", "bundle", "--version"),
    },
}


def entry_for(key: str, tag: str | None = None) -> Download | None:
    """Cosa scaricare per questo componente su questa piattaforma, o None se
    non abbiamo una build: non è un errore, è un caso da mostrare all'utente
    insieme al comando manuale."""
    return MANIFEST.get(key, {}).get(tag or platform_tag())
