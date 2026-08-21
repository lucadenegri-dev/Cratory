"""Il confronto è numerico, non testuale. È il difetto classico di questa
funzione e vale la pena avere un test che lo nomina."""
from app.core.version import is_newer, parse_version


def test_dieci_viene_dopo_nove():
    """Come stringhe "0.10.0" < "0.9.0": un confronto testuale direbbe che
    la 0.10.0 è più vecchia, e l'utente non vedrebbe mai l'aggiornamento."""
    assert is_newer("0.10.0", "0.9.0") is True
    assert is_newer("0.9.0", "0.10.0") is False


def test_uguale_non_e_piu_recente():
    assert is_newer("0.9.0", "0.9.0") is False


def test_il_prefisso_v_dei_tag_viene_tolto():
    """I tag git portano la `v`, il file VERSION no: il confronto avviene fra
    cose che devono prima essere ridotte alla stessa forma."""
    assert parse_version("v0.9.0") == (0, 9, 0)
    assert is_newer("v0.10.0", "0.9.0") is True


def test_maggiore_su_ogni_posizione():
    assert is_newer("1.0.0", "0.99.99") is True
    assert is_newer("0.9.1", "0.9.0") is True


def test_il_suffisso_di_prerelease_non_rompe():
    assert parse_version("1.0.0-beta.1") == (1, 0, 0)


def test_versione_malformata_non_solleva():
    """Un tag lo scrive una persona a mano: può essere qualunque cosa."""
    for scritto_male in ("", "boh", "1.2", "1.2.3.4", "v", "x.y.z"):
        assert parse_version(scritto_male) is None
        assert is_newer(scritto_male, "0.9.0") is False
        assert is_newer("0.9.0", scritto_male) is False
