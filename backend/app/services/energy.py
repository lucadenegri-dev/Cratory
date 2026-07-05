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
