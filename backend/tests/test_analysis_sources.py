"""Regole di provenienza: modifica manuale (repositories.update_track)."""
from app.models import Track
from app.repositories import update_track


def test_patch_bpm_imposta_source_manual(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": 130.0})
    assert t.bpm == 130.0 and t.bpm_source == "manual"


def test_patch_key_imposta_source_manual(db):
    t = Track(source_type="spotify", camelot_key="8A", key_source="cratory")
    db.add(t); db.commit()
    update_track(db, t, {"camelot_key": "9A"})
    assert t.camelot_key == "9A" and t.key_source == "manual"


def test_azzeramento_azzera_anche_la_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="manual",
              camelot_key="8A", key_source="manual")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": None, "camelot_key": None})
    assert t.bpm is None and t.bpm_source is None
    assert t.camelot_key is None and t.key_source is None


def test_patch_altri_campi_non_tocca_le_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"title": "Nuovo"})
    assert t.bpm_source == "rekordbox"


# ---- Import Rekordbox source-aware (services/rekordbox_import) ----

def _xml(bpm="130.00", tonality="9A", path="/x/a.mp3"):
    loc = f"file://localhost{path}"
    return (f'<DJ_PLAYLISTS><COLLECTION><TRACK Location="{loc}" '
            f'AverageBpm="{bpm}" Tonality="{tonality}" Artist="A" Name="T"/>'
            f"</COLLECTION></DJ_PLAYLISTS>").encode()


def _owned(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", has_local_file=True, local_path="/x/a.mp3",
              artist="A", title="T", **kw)
    db.add(t); db.commit()
    return t


def test_rekordbox_sovrascrive_cratory_di_default(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="cratory", camelot_key="8A", key_source="cratory")
    apply_collection(db, _xml())
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"


def test_rekordbox_protegge_manual_di_default(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="manual", camelot_key="8A", key_source="manual")
    apply_collection(db, _xml())
    assert t.bpm == 127.5 and t.bpm_source == "manual"
    assert t.camelot_key == "8A" and t.key_source == "manual"


def test_rekordbox_overwrite_vince_anche_su_manual(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="manual", camelot_key="8A", key_source="manual")
    apply_collection(db, _xml(), overwrite=True)
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"


def test_rekordbox_riempie_campi_vuoti_con_source(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db)
    apply_collection(db, _xml())
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"


def test_rekordbox_riallinea_la_fonte_quando_conferma_il_valore(db):
    """Il rilievo, misurato sul DB di produzione: 147 key e 21 BPM identici a
    quelli di Rekordbox restavano etichettati `cratory`, perche' la scrittura
    era condizionata alla DIFFERENZA del valore.

    Due danni. Il primo e' visibile: i contatori per fonte della pagina
    Analisi non si muovono dopo un import — "ho importato e non cambia
    niente". Il secondo e' peggio: quei valori restano dichiarati come stime
    dell'analisi, quindi tutto cio' che rispetta la gerarchia (l'import
    stesso, l'apply in blocco) li tratta come sacrificabili quando invece
    Rekordbox li ha appena confermati.
    """
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=130.0, bpm_source="cratory", camelot_key="9A", key_source="cratory")
    esito = apply_collection(db, _xml())
    assert (t.bpm, t.camelot_key) == (130.0, "9A")      # il valore non cambia
    assert t.bpm_source == "rekordbox" and t.key_source == "rekordbox"
    # Non e' una scrittura di valore: i contatori esistenti non devono gonfiarsi.
    assert (esito["bpm_set"], esito["key_set"]) == (0, 0)
    assert esito["source_realigned"] == 1


def test_il_riallineamento_non_declassa_una_correzione_manuale(db):
    """Confermare un valore non e' scavalcarlo: `manual` sta sopra `rekordbox`
    nella gerarchia, e un import che passa non deve riscriverne l'etichetta."""
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=130.0, bpm_source="manual", camelot_key="9A", key_source="manual")
    esito = apply_collection(db, _xml())
    assert t.bpm_source == "manual" and t.key_source == "manual"
    assert esito["source_realigned"] == 0


# ---- L'apply dell'analisi rispetta la gerarchia (services/audio_analysis) ----


def _analizzata(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", has_local_file=True, local_path="/x/b.mp3",
              artist="A", title="T", analysis_bpm=130.0, analysis_camelot="9A", **kw)
    db.add(t); db.commit()
    return t


def test_l_apply_in_blocco_non_declassa_rekordbox(db):
    """Cio' che e' costato l'import di stamattina: un apply in blocco ha
    riscritto 275 tracce con le stime dell'analisi, cancellando i BPM/key
    appena importati. La regola 2 dice manual > rekordbox > cratory, e l'apply
    non la applicava affatto."""
    from app.services.audio_analysis import apply_analysis
    t = _analizzata(db, bpm=128.0, bpm_source="rekordbox",
                    camelot_key="8A", key_source="rekordbox")
    assert apply_analysis(t) is False
    assert (t.bpm, t.camelot_key) == (128.0, "8A")
    assert (t.bpm_source, t.key_source) == ("rekordbox", "rekordbox")


def test_l_apply_in_blocco_riscrive_comunque_i_valori_dell_analisi(db):
    """La guardia non deve immobilizzare il caso normale: su un valore che
    viene gia' dall'analisi, riapplicare e' esattamente il lavoro."""
    from app.services.audio_analysis import apply_analysis
    t = _analizzata(db, bpm=128.0, bpm_source="cratory",
                    camelot_key="8A", key_source="cratory")
    assert apply_analysis(t) is True
    assert (t.bpm, t.camelot_key) == (130.0, "9A")


def test_l_apply_in_blocco_riempie_i_campi_vuoti(db):
    """Un campo vuoto non ha una fonte da declassare."""
    from app.services.audio_analysis import apply_analysis
    t = _analizzata(db)
    assert apply_analysis(t) is True
    assert (t.bpm, t.bpm_source) == (130.0, "cratory")
    assert (t.camelot_key, t.key_source) == ("9A", "cratory")


def test_l_apply_su_una_traccia_scelta_scavalca_la_fonte(db):
    """La via d'uscita resta, ma una traccia alla volta: nella lista divergenze
    ogni riga mostra la propria fonte, quindi la scelta e' informata."""
    from app.services.audio_analysis import apply_analysis
    t = _analizzata(db, bpm=128.0, bpm_source="rekordbox",
                    camelot_key="8A", key_source="manual")
    assert apply_analysis(t, respect_source=False) is True
    assert (t.bpm, t.bpm_source) == (130.0, "cratory")
    assert (t.camelot_key, t.key_source) == ("9A", "cratory")
