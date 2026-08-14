"""Indicizzazione della libreria canonica (LIBRARY_ROOT)."""
import pytest

from app.core.config import Settings


def test_library_root_default_vuoto(monkeypatch):
    # Isola dal vero LIBRARY_ROOT dello sviluppatore: app/main.py ora fa
    # load_dotenv(backend/.env) (serve ad ANTHROPIC_API_KEY per l'SDK
    # Anthropic), quindi da quando il modulo e' stato importato la variabile
    # e' anche nel process env — _env_file=None da solo non basta più.
    monkeypatch.delenv("LIBRARY_ROOT", raising=False)
    s = Settings(_env_file=None)
    assert s.library_root == ""


def test_riaggancio_per_audio_hash(db, fake_audio, collega_da_disco):
    """File rinominato/ritaggato: stesso hash ⇒ stessa Track, local_path aggiornato."""
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", spotify_id="s1", title="Origin", artist="A",
              has_local_file=True, local_path="/vecchio/inbox/file.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Techno/A/A - Origin.mp3", digest="H1")
    report = collega_da_disco(root)

    db.refresh(t)
    assert report["relinked"] == 1 and report["created"] == 0
    assert t.local_path.endswith("A - Origin.mp3")
    assert t.has_local_file is True and t.local_format == "mp3"


def test_indicizzazione_backfilla_label_da_tag(db, fake_audio, collega_da_disco):
    """La label del file (TPUB) riempie il campo label se vuoto (backfill-only)."""
    from app.models import Track

    make, root = fake_audio
    make("Warp/Aphex - Xtal.mp3", digest="HL", artist="Aphex Twin", title="Xtal", label="Warp")
    collega_da_disco(root)

    t = db.query(Track).filter_by(audio_hash="HL").one()
    assert t.label == "Warp"


def test_match_per_isrc_da_tag(db, fake_audio, collega_da_disco):
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", isrc="ISRC001", title="X", artist="A")
    db.add(t); db.commit()

    make("f.mp3", digest="H9", isrc="ISRC001")
    collega_da_disco(root)

    db.refresh(t)
    assert t.has_local_file is True and t.audio_hash == "H9"


def test_match_fuzzy_artista_titolo(db, fake_audio, collega_da_disco):
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", title="My Song", artist="Someone")
    db.add(t); db.commit()

    make("g.mp3", digest="H8", artist="someone", title="my song")
    collega_da_disco(root)

    db.refresh(t)
    assert t.has_local_file is True


def test_file_sconosciuto_crea_track_local_files(db, fake_audio, collega_da_disco):
    from sqlalchemy import select
    from app.models import Track

    make, root = fake_audio
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    report = collega_da_disco(root)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"
    assert t.platform_track_id == "H7" and t.artist == "N"


def test_non_sovrascrive_identita_esistente(db, fake_audio, collega_da_disco):
    """I tag del file riempiono solo i campi vuoti (l'enrichment/manuale resta autorevole)."""
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", title="Titolo Corretto", artist="A",
              genre="Techno", audio_hash="H1")
    db.add(t); db.commit()

    make("f.mp3", digest="H1", artist="A", title="titolo sbagliato dal tag")
    collega_da_disco(root)

    db.refresh(t)
    assert t.title == "Titolo Corretto" and t.genre == "Techno"


def test_lead_con_genere_si_allinea_al_tag_del_file_quando_acquisisce_un_possesso(
        db, fake_audio, collega_da_disco):
    """D8: `_fill_identity` riempie il genere SOLO se vuoto ("mai
    sovrascrivere"), quindi da sola non basta quando il lead arriva gia' con
    un genere (streaming): senza la regola condivisa resterebbe "Electronic"
    per sempre anche se il file dice "Techno". Stessa regola di
    genre_align.align_track_genre gia' usata da Apply/scan/modifica manuale,
    applicata qui al momento in cui l'aggancio nasce."""
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", isrc="ISRC001", title="X", artist="A",
             genre="Electronic")
    db.add(t); db.commit()

    make("f.mp3", digest="H9", isrc="ISRC001", genre="Techno")
    collega_da_disco(root)

    db.refresh(t)
    assert t.has_local_file is True
    assert t.genre == "Techno"


def test_align_track_genre_ricalcola_energia(db):
    """Contratto di `genre_align.align_track_genre` (docstring, righe 48-49):
    con `apply=True`, oltre a scrivere `track.genre`, ricalcola l'energia
    derivata perche' `energy` dipende da bpm+genere. `energy_source` diventa
    'estimated' (mai 'computed', riservato all'analisi Essentia). Chiamata
    diretta sulla funzione condivisa da tutti e cinque i call site di
    produzione (scanner/manual_edit/apply/library_index/acquisition): nessuno
    di quei call site asserisce sull'energia, solo su `genre`.

    L'energia parte gia' seminata sul genere VECCHIO (non su None): altrimenti
    `t.energy != before_energy` si riduce a un controllo di non-nullita' e
    passerebbe anche se il ricalcolo leggesse il genere sbagliato (es. un
    riordino che ricalcola prima di scrivere `track.genre`) — l'invariante
    da proteggere e' che l'energia rifletta il genere NUOVO, non che sia
    stata scritta. Derivare entrambi i valori da `estimate_energy` invece di
    cablare le costanti tiene il test agganciato all'invariante, non alla
    formula. Effetto collaterale utile: seminare l'energia copre anche il
    ritorno anticipato di `apply_estimated_energy` quando il valore
    ricalcolato coincide con quello gia' presente (`energy.py:24`) — un
    percorso irraggiungibile partendo da `energy=None`."""
    from app.models import Track
    from app.services.energy import estimate_energy
    from app.services.genre_align import align_track_genre

    t = Track(source_type="local_files", has_local_file=True,
              genre="Electronic", bpm=128.0,
              energy=estimate_energy(128.0, None, "Electronic"),
              energy_source="estimated")
    db.add(t); db.commit()

    new_genre = align_track_genre(t, "Techno", apply=True)

    assert new_genre == "Techno"
    assert t.genre == "Techno"
    assert t.energy == estimate_energy(128.0, None, "Techno")  # segue il genere NUOVO
    assert t.energy_source == "estimated"


def test_align_track_genre_file_vuoto_non_tocca(db):
    """Guardia di `genre_align.align_track_genre` (righe 54-55): se il tag genere
    del file normalizza a vuoto (`None`, stringa vuota, o solo spazi/trattini —
    tutto cio' che `normalize_genre` riduce a niente), la funzione ritorna `None`
    e non tocca `track.genre` ne' l'energia derivata. E' la guardia simmetrica a
    quella coperta da `test_align_track_genre_ricalcola_energia` qui sopra: quel
    test prova che un tag valido *aggiorna* genere+energia, questo prova che un
    tag vuoto lascia *entrambi* al valore di streaming — un file non taggato non
    deve azzerare un genere gia' noto.

    L'energia parte gia' seminata (stesso motivo del test sopra: partire da
    `energy=None` renderebbe "non tocca" indistinguibile da "non ha ricalcolato
    nulla perche' non c'era nulla da ricalcolare")."""
    from app.models import Track
    from app.services.energy import estimate_energy
    from app.services.genre_align import align_track_genre

    seeded_energy = estimate_energy(128.0, None, "Electronic")
    t = Track(source_type="spotify", genre="Electronic", bpm=128.0,
              energy=seeded_energy, energy_source="estimated")
    db.add(t); db.commit()

    result = align_track_genre(t, "  -  ", apply=True)

    assert result is None
    assert t.genre == "Electronic"
    assert t.energy == seeded_energy
    assert t.energy_source == "estimated"


def test_duplicati_stesso_run_primo_vince(db, fake_audio, collega_da_disco):
    """Stesso audio in due file: il primo vince, il secondo si conta come duplicato."""
    from sqlalchemy import select
    from app.models import Track

    make, root = fake_audio
    make("a.mp3", digest="HD", artist="A", title="Dup")
    make("b.mp3", digest="HD", artist="A", title="Dup")
    report = collega_da_disco(root)

    assert report["created"] == 1 and report["duplicates"] == 1
    assert report["relinked"] == 0
    t = db.scalar(select(Track).where(Track.audio_hash == "HD"))
    assert t.local_path.endswith("a.mp3")  # scan_folder ordina: il primo file vince


def test_riconciliazione_sgancia_ma_tiene_se_in_playlist(db, fake_audio, collega_da_disco, tmp_path):
    """File sparito ma traccia in una playlist ⇒ si toglie solo il link (resta lead),
    hash conservato per il riaggancio futuro."""
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist

    make, root = fake_audio
    pl = Playlist(platform="spotify", name="P"); db.add(pl)
    sparito = Track(source_type="spotify", title="Gone", artist="A",
                    has_local_file=True, local_path=str(tmp_path / "non-esiste.mp3"),
                    local_format="mp3", audio_hash="HGONE")
    db.add(sparito); db.flush()
    add_track_to_playlist(db, sparito, pl); db.commit()

    make("resta.mp3", digest="HSTAY", artist="B", title="Stay")
    report = collega_da_disco(root)

    db.refresh(sparito)
    assert report["lost"] == 1 and report["orphans_removed"] == 0
    assert sparito.has_local_file is False and sparito.local_path is None
    assert sparito.audio_hash == "HGONE"


def test_riconciliazione_elimina_lost_orfano(db, fake_audio, collega_da_disco, tmp_path):
    """File sparito e traccia in nessuna playlist/set ⇒ rimossa (niente lead fantasma)."""
    from app.models import Track

    make, root = fake_audio
    orfano = Track(source_type="local_files", title="Ghost", artist="A",
                   has_local_file=True, local_path=str(tmp_path / "sparito.mp3"), audio_hash="HG")
    db.add(orfano); db.commit()
    gid = orfano.id

    make("resta.mp3", digest="HSTAY")
    report = collega_da_disco(root)

    assert report["orphans_removed"] == 1 and report["lost"] == 0
    assert db.get(Track, gid) is None


def test_riconciliazione_sgancia_file_in_cartella_nascosta(db, fake_audio, collega_da_disco, tmp_path):
    """File esistente ma dentro una cartella nascosta (scan_folder lo esclude) ⇒
    non più posseduto; il file su disco non viene toccato."""
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist

    make, root = fake_audio
    make("visibile.mp3", digest="HV")  # scan non vuoto (evita l'anti-unmount)
    hidden = tmp_path / ".q" / "nascosto.mp3"
    hidden.parent.mkdir(parents=True)
    hidden.write_bytes(b"x")
    pl = Playlist(platform="spotify", name="P"); db.add(pl)
    t = Track(source_type="local_files", title="Hidden", artist="A",
              has_local_file=True, local_path=str(hidden.resolve()), audio_hash="HH")
    db.add(t); db.flush()
    add_track_to_playlist(db, t, pl); db.commit()

    collega_da_disco(root)

    db.refresh(t)
    assert t.has_local_file is False
    assert hidden.exists()  # Cratory non muta i file su disco


def test_fuzzy_normalizzato_aggancia_titolo_con_suffissi(db, fake_audio, collega_da_disco):
    """File 'X feat. Y (Original Mix)' si aggancia al lead Spotify 'X' (stesso
    artista, durata coerente) invece di creare un doppione."""
    from app.models import Track

    make, root = fake_audio
    lead = Track(source_type="spotify", spotify_id="s1", title="Rápido & Lento ;)",
                 artist="Brenda, Verraco", duration_seconds=200, has_local_file=False)
    db.add(lead); db.commit()
    lid = lead.id

    make("f.mp3", digest="HFZ", artist="Brenda, Verraco",
         title="Rápido & Lento ;) feat. Verraco (Original Mix)")
    report = collega_da_disco(root)

    db.refresh(lead)
    assert report["created"] == 0 and report["matched"] == 1
    assert lead.id == lid and lead.has_local_file is True


def test_fuzzy_normalizzato_rispetta_la_guardia_durata(db, fake_audio, collega_da_disco):
    """Durata troppo diversa (brano vs suo remix esteso) ⇒ NON si fonde."""
    from app.models import Track

    make, root = fake_audio
    lead = Track(source_type="spotify", title="Song", artist="A",
                 duration_seconds=120, has_local_file=False)
    db.add(lead); db.commit()

    make("f.mp3", digest="HG", artist="A", title="Song (Extended Mix)")  # tags: duration 200
    report = collega_da_disco(root)

    db.refresh(lead)
    assert report["created"] == 1 and lead.has_local_file is False


def test_file_che_rientra_si_riaggancia_al_lead_spotify(db, fake_audio, collega_da_disco):
    """Un file che (ri)entra nella libreria si aggancia al lead Spotify per ISRC:
    stessa riga, ora posseduta, ancora nella playlist."""
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist, tracks_for_playlist

    make, root = fake_audio
    pl = Playlist(platform="spotify", name="P"); db.add(pl)
    lead = Track(source_type="spotify", platform="spotify", spotify_id="s1",
                 title="Song", artist="Artist", isrc="IT1234500001", has_local_file=False)
    db.add(lead); db.flush()
    add_track_to_playlist(db, lead, pl); db.commit()
    lid = lead.id

    make("Artist - Song.mp3", digest="HNEW", isrc="IT1234500001")
    report = collega_da_disco(root)

    db.refresh(lead)
    assert report["created"] == 0 and report["matched"] == 1  # riaggancio, non nuova traccia
    assert lead.id == lid and lead.has_local_file is True
    assert lead in tracks_for_playlist(db, pl.id)


def test_riconciliazione_non_tocca_i_visti(db, fake_audio, collega_da_disco):
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", title="Here", artist="A", audio_hash="H1")
    db.add(t); db.commit()
    make("here.mp3", digest="H1")
    report = collega_da_disco(root)

    db.refresh(t)
    assert report["lost"] == 0 and t.has_local_file is True


def test_radice_vuota_non_azzera_i_possessi(db, fake_audio, collega_da_disco, tmp_path):
    """Anti-unmount: scan a zero file (root sbagliata/smontata) salta la riconciliazione."""
    from app.models import Track

    make, root = fake_audio
    t = Track(source_type="spotify", title="Keep", artist="A",
              has_local_file=True, local_path=str(tmp_path / "sparito.mp3"),
              audio_hash="HK")
    db.add(t); db.commit()

    vuota = tmp_path / "radice-vuota"
    vuota.mkdir()
    report = collega_da_disco(vuota)

    db.refresh(t)
    assert report["lost"] == 0
    assert t.has_local_file is True  # nessuna riconciliazione su scan vuoto


def test_energia_non_ricalcolata_su_indice_vuoto(db, monkeypatch):
    """Anti-unmount, versione wrapper: un indice di libreria vuoto (nessuna riga
    AudioFile — scan mai passato, o radice smontata) non deve nemmeno
    ricalcolare l'energia. Prima di F4 il return anticipato di `index_library`
    usciva anche da qui; con `collega_tracce` che fa il return anticipato al
    suo interno, il wrapper continuava fino a `recompute_energy` comunque."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    calls: list[int] = []
    monkeypatch.setattr(li, "recompute_energy", lambda db: calls.append(1) or 0)

    report = index_library(db)  # nessuna riga AudioFile in un DB vuoto

    assert calls == []
    assert "energy_computed" not in report


def test_report_indice_contiene_created_ids(db, tmp_path, monkeypatch, collega_da_disco):
    """Il report espone gli id delle Track create: il chiamante (job in background)
    li usa per agire sulle tracce nuove appena indicizzate."""
    from app.services import library_index as li

    p = tmp_path / "Libreria" / "A - Nuova.mp3"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    monkeypatch.setattr(li, "audio_hash", lambda _: "H-NEW")
    monkeypatch.setattr(li, "read_tags", lambda _: {
        "title": "Nuova", "artist": "A", "album": None, "year": None,
        "duration_seconds": 200, "isrc": None, "genre": None})
    monkeypatch.setattr(li, "read_audio_quality", lambda _: {"format": "mp3", "bitrate": 320})

    report = collega_da_disco(tmp_path / "Libreria")
    assert report["created"] == 1
    assert len(report["created_ids"]) == 1


def test_indicizzazione_backfilla_added_at_dal_birthtime(db, fake_audio, collega_da_disco, monkeypatch):
    """Traccia senza data: l'indice la data dal birthtime del file (recupero
    per le storiche); chi ha già una data non viene mai retrodatato."""
    from datetime import datetime, timezone

    from app.models import Track
    from app.services import library_index as li

    birth = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(li, "_file_added_at", lambda p: birth)

    senza = Track(source_type="local_files", title="Senza", artist="A",
                  has_local_file=True, local_path="/vecchio/a.mp3", audio_hash="H1")
    con = Track(source_type="spotify", spotify_id="s1", title="Con", artist="A",
                has_local_file=True, local_path="/vecchio/b.mp3", audio_hash="H2",
                added_at=datetime(2025, 1, 1))
    db.add_all([senza, con]); db.commit()

    make, root = fake_audio
    make("A/A - Senza.mp3", digest="H1")
    make("A/A - Con.mp3", digest="H2")
    collega_da_disco(root)

    db.refresh(senza); db.refresh(con)
    assert senza.added_at is not None and str(senza.added_at).startswith("2026-06-27")
    assert str(con.added_at).startswith("2025-01-01")


def test_backfill_added_at_anche_sul_fast_path_incrementale(db, fake_audio, collega_da_disco, monkeypatch):
    """File invariato (mtime+size noti): niente ri-hash, ma la traccia storica
    senza data viene comunque datata dal birthtime."""
    from datetime import datetime, timezone

    from app.models import Track
    from app.services import library_index as li

    birth = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(li, "_added_at_from_stat", lambda st: birth)

    make, root = fake_audio
    p = make("A/A - Invariata.mp3", digest="H1")
    stat = p.stat()
    t = Track(source_type="local_files", title="Invariata", artist="A",
              has_local_file=True, local_path=str(p.resolve()), audio_hash="H1",
              local_mtime=stat.st_mtime, local_size=stat.st_size)
    db.add(t); db.commit()

    report = collega_da_disco(root)

    db.refresh(t)
    assert report["unchanged"] == 1
    assert t.added_at is not None and str(t.added_at).startswith("2026-06-27")


def test_non_conia_una_track_per_un_path_gia_posseduto(db, fake_audio, collega_da_disco):
    """Regressione (fine F3b): un Apply di Organize cambia mtime e size, quindi
    il fast-path della passata 1 salta; l'hash ricalcolato non combacia piu' con
    quello memorizzato, il file non porta l'ISRC e i rami per nome escludono le
    tracce gia' possedute. Prima del fix si coniava una Track local_files per un
    path che un'altra Track rivendicava gia'."""
    from sqlalchemy import select

    from app.models import Track

    make, root = fake_audio
    p = make("Trance/R/R - Aqua Viva.mp3", digest="H_NUOVO", artist="R", title="Aqua Viva")
    t = Track(source_type="spotify", spotify_id="s1", isrc="BEZ350900033",
              artist="R", title="Aqua Viva", has_local_file=True,
              local_path=str(p.resolve()), audio_hash="H_VECCHIO")
    db.add(t)
    db.commit()

    report = collega_da_disco(root)

    assert report["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1
    db.refresh(t)
    assert t.audio_hash == "H_NUOVO"      # l'identita' audio si aggiorna
