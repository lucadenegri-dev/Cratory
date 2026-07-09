"""Stima deterministica dell'energia (0-100) da BPM + genere (+ danceability se nota).
Spostata da feature_enrichment: NON è enrichment da provider, è un proxy derivato.
Ricalcolata all'import Rekordbox (slice 2) sui BPM veri."""

_HIGH_ENERGY_GENRES = (
    "techno", "hardcore", "hardstyle", "drum and bass", "dnb", "trance", "rave",
    "gabber", "acid", "industrial", "schranz", "speed garage", "bass", "hard",
)
_LOW_ENERGY_GENRES = (
    "ambient", "chill", "downtempo", "lo-fi", "lofi", "dub", "deep house",
    "minimal", "jazz", "soul", "acoustic", "ballad", "lounge",
)


def apply_estimated_energy(track) -> bool:
    """Applica l'energia-proxy (da BPM/genere) a `track`, MA senza calpestare un
    valore calcolato dai file audio (energy_source='computed' vince). Imposta
    energy_source='estimated' quando scrive. Ritorna True se ha cambiato l'energia.
    """
    if getattr(track, "energy_source", None) == "computed" or track.bpm is None:
        return False
    value = estimate_energy(track.bpm, None, track.genre)
    if value is None or value == track.energy:
        return False
    track.energy = value
    track.energy_source = "estimated"
    return True


def estimate_energy(bpm, danceability, genre):
    if bpm is None:
        return None
    energy = max(0.0, min(100.0, (bpm - 110.0) / 30.0 * 100.0))
    if danceability is not None:
        energy = 0.6 * energy + 0.4 * danceability
    g = (genre or "").lower()
    if any(k in g for k in _HIGH_ENERGY_GENRES):
        energy += 12
    elif any(k in g for k in _LOW_ENERGY_GENRES):
        energy -= 12
    return int(max(0, min(100, round(energy))))
