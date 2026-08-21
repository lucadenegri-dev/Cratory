"""Verifiche della guardia che impedisce l'esecuzione accidentale di package manager.

IMPORTANTE: questi test eseguono INTENZIONALMENTE subprocess.run() e subprocess.Popen()
su comandi package manager SENZA mock. L'unico scopo è verificare che la guardia nel
conftest li blocchi.

In tutti gli altri test della suite, qualsiasi tentativo di lanciare un package manager
viene fermato e fallisce con un messaggio di errore, non silenziosamente permesso.
"""
import subprocess

import pytest


class TestGuardiaPackageManager:
    """Verifiche che la guardia blocca l'esecuzione di package manager."""

    def test_guardia_blocca_brew_con_subprocess_run(self):
        """Tentativo di lanciare `brew` via subprocess.run() senza mock fallisce."""
        with pytest.raises(RuntimeError, match=r"SICUREZZA.*brew"):
            subprocess.run(["brew", "install", "ffmpeg"], check=False)

    def test_guardia_blocca_brew_con_subprocess_popen(self):
        """Tentativo di lanciare `brew` via subprocess.Popen() senza mock fallisce."""
        with pytest.raises(RuntimeError, match=r"SICUREZZA.*brew"):
            subprocess.Popen(["brew", "install", "ffmpeg"])

    def test_guardia_blocca_apt_con_subprocess_run(self):
        """Tentativo di lanciare `apt` via subprocess.run() senza mock fallisce."""
        with pytest.raises(RuntimeError, match=r"SICUREZZA.*apt"):
            subprocess.run(["apt", "install", "ffmpeg"], check=False)

    def test_guardia_blocca_sudo_apt_con_subprocess_run(self):
        """Tentativo di lanciare `sudo apt` via subprocess.run() senza mock fallisce."""
        with pytest.raises(RuntimeError, match=r"SICUREZZA.*sudo"):
            subprocess.run(["sudo", "apt", "install", "ffmpeg"], check=False)

    def test_guardia_blocca_winget_con_subprocess_run(self):
        """Tentativo di lanciare `winget` via subprocess.run() senza mock fallisce."""
        with pytest.raises(RuntimeError, match=r"SICUREZZA.*winget"):
            subprocess.run(["winget", "install", "ffmpeg"], check=False)

    def test_guardia_permette_ffmpeg_legittimo_con_subprocess_run(self):
        """I tool legittimi come ffmpeg passano attraverso. La guardia li permette."""
        # ffmpeg è installato sul sistema, quindi il comando avrà successo
        # e non solleverà nulla. La guardia non lo blocca.
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
        # Se fosse arrivato qui, la guardia non lo ha bloccato (bene!)
        assert result.returncode == 0

    def test_guardia_permette_fpcalc_legittimo_con_subprocess_run(self):
        """fpcalc è un tool legittimo, non un package manager: passa attraverso."""
        # Se fpcalc non è installato fallirà con uno stato non-zero ma la guardia
        # non lo blocca. Se lo è, succederà con successo. Comunque sia, il punto è
        # che RuntimeError della guardia NON verrà sollevato.
        result = subprocess.run(["fpcalc", "-version"], capture_output=True, check=False)
        # Non dovrebbe essere RuntimeError della guardia, quindi se arriviamo qui vincere.
        # La guardia ha permesso il tentativo (anche se fallisce successivamente).
        assert isinstance(result, subprocess.CompletedProcess)
