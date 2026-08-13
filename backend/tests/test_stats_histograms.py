"""Aggregatori deterministici per la dashboard: istogramma BPM e distribuzione energia."""

from app.repositories import _bpm_histogram, _energy_distribution


def test_bpm_histogram_empty():
    assert _bpm_histogram([]) == []


def test_bpm_histogram_single_value():
    bins = _bpm_histogram([128.0, 128.0, 128.0])
    assert bins == [{"from": 128.0, "to": 128.0, "count": 3}]


def test_bpm_histogram_eight_equal_bins():
    bpms = [100.0, 105.0, 120.0, 135.0, 150.0, 165.0, 179.0, 180.0]
    bins = _bpm_histogram(bpms)
    assert len(bins) == 8
    # estremi ai bordi della libreria
    assert bins[0]["from"] == 100.0
    assert bins[-1]["to"] == 180.0
    # ogni traccia conteggiata una sola volta
    assert sum(b["count"] for b in bins) == len(bpms)
    # il valore massimo cade nell'ultimo bin (chiuso a destra)
    assert bins[-1]["count"] >= 1


def test_bpm_histogram_bin_width_consistent():
    bins = _bpm_histogram([60.0, 140.0])  # range 80 / 8 = width 10
    widths = [round(b["to"] - b["from"], 6) for b in bins]
    assert widths == [10.0] * 8


def test_energy_distribution_five_fixed_buckets_when_empty():
    buckets = _energy_distribution([])
    assert [b["from"] for b in buckets] == [0, 20, 40, 60, 80]
    assert [b["to"] for b in buckets] == [20, 40, 60, 80, 100]
    assert all(b["count"] == 0 for b in buckets)


def test_energy_distribution_boundaries():
    # 0 -> [0,20]; 20 -> [20,40]; 100 -> [80,100]
    buckets = _energy_distribution([0, 20, 40, 60, 80, 100, 100])
    counts = [b["count"] for b in buckets]
    assert counts == [1, 1, 1, 1, 3]


def test_stats_with_local_file(db):
    from app.models import Track
    from app.repositories import library_stats

    db.add(Track(source_type="spotify", title="O", artist="A", has_local_file=True))
    db.add(Track(source_type="spotify", title="W", artist="B"))
    db.commit()
    assert library_stats(db)["with_local_file"] == 1


def test_genre_distribution_usa_il_valore_effettivo(db):
    """F2: genre_distribution deve contare il genere EFFETTIVO (tag del file
    quando la traccia ne ha uno), come /api/library/genres e come il filtro
    /library?genre=<g> a cui la dashboard e la pagina etichette linkano
    quelle barre. Aggregare sulla sola colonna streaming (Track.genre)
    produce un numero diverso da quello che il click sulla barra restituisce."""
    from app.models import Track
    from app.organize.models import AudioFile, ScanRoot
    from app.repositories import library_stats

    root = ScanRoot(path="/tmp/lib-genre-dist")
    db.add(root)
    db.flush()

    # Track.genre="Pop" mascherato dal tag file "Techno": non deve contare come Pop.
    t1 = Track(source_type="spotify", title="T1", artist="A1", genre="Pop")
    db.add(t1)
    db.flush()
    f1 = AudioFile(root_id=root.id, track_id=t1.id, path="/tmp/lib-genre-dist/1.mp3",
                   ext=".mp3", size_bytes=1, hash_method="stream", status="present",
                   location="library", genre="Techno")
    db.add(f1)
    db.flush()
    t1.primary_file_id = f1.id
    t1.has_local_file = True

    # Genere presente SOLO sul file (Track.genre vuoto): deve comunque comparire.
    t2 = Track(source_type="spotify", title="T2", artist="A2")
    db.add(t2)
    db.flush()
    f2 = AudioFile(root_id=root.id, track_id=t2.id, path="/tmp/lib-genre-dist/2.mp3",
                   ext=".mp3", size_bytes=1, hash_method="stream", status="present",
                   location="library", genre="Techno")
    db.add(f2)
    db.flush()
    t2.primary_file_id = f2.id
    t2.has_local_file = True

    # Traccia senza file: il genere streaming resta l'unica fonte.
    db.add(Track(source_type="spotify", title="T3", artist="A3", genre="House"))
    db.commit()

    dist = library_stats(db)["genre_distribution"]
    assert dist == {"Techno": 2, "House": 1}
    assert "Pop" not in dist  # mascherato dal tag file, non deve comparire
