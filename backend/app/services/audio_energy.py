"""Energia vera dai file audio (PR4).

Motore deterministico (niente AI): dai campioni PCM già decodificati da ffmpeg
durante l'indicizzazione, estrae tre feature — RMS (quanto spinge), centroide
spettrale (brillantezza/aggressività), flusso spettrale (densità di transienti) —
le combina in un `energy_raw` per-file (0..1) e poi calibra `energy` (0-100) per
percentili sulla libreria dell'utente. Nessuna nuova dipendenza: ffmpeg e numpy
sono già presenti; i tag li scrive solo Sortory, qui si legge soltanto.
"""

import numpy as np

SR = 22050          # frequenza dei PCM prodotti da audio_hash (mono s16le)
_FRAME = 1024
_HOP = 512
_INT16_MAX = 32768.0
_FLUX_REF = 0.6     # normalizzazione empirica del flusso in 0..1 (poi la calibrazione
#                     a percentili rende il valore assoluto poco critico)

# Pesi della combinazione. Centroide+flusso pesano parecchio di proposito: dipendono
# dal CONTENUTO, non dal livello di mastering, quindi riducono il bias del solo RMS.
_W_RMS = 0.4
_W_CENTROID = 0.35
_W_FLUX = 0.25


def pcm_features(samples: np.ndarray) -> tuple[float, float, float]:
    """(rms 0..1, centroide Hz, flusso) da un array PCM int16 mono a SR Hz."""
    x = np.asarray(samples, dtype=np.float64)
    if x.size == 0:
        return 0.0, 0.0, 0.0
    x /= _INT16_MAX
    rms = float(np.sqrt(np.mean(x * x)))

    if x.size < _FRAME:
        x = np.pad(x, (0, _FRAME - x.size))
    win = np.hanning(_FRAME)
    starts = range(0, x.size - _FRAME + 1, _HOP)
    mags = np.array([np.abs(np.fft.rfft(x[s:s + _FRAME] * win)) for s in starts])
    freqs = np.fft.rfftfreq(_FRAME, 1.0 / SR)

    frame_energy = mags.sum(axis=1) + 1e-9
    centroids = (mags * freqs).sum(axis=1) / frame_energy
    centroid = float(np.average(centroids, weights=frame_energy))

    if len(mags) > 1:
        rising = np.maximum(np.diff(mags, axis=0), 0.0).sum(axis=1)
        flux = float(np.mean(rising / frame_energy[1:]))
    else:
        flux = 0.0
    return rms, centroid, flux


def combine_features(rms: float, centroid: float, flux: float) -> float:
    """Combina le feature grezze in un `energy_raw` per-file (0..1)."""
    rms_n = min(1.0, max(0.0, rms))
    centroid_n = min(1.0, max(0.0, centroid / (SR / 2.0)))
    flux_n = min(1.0, max(0.0, flux / _FLUX_REF))
    return _W_RMS * rms_n + _W_CENTROID * centroid_n + _W_FLUX * flux_n


WINDOW_SECONDS = 20  # durata di ciascuna finestra analizzata


def _window_offsets(duration: float | None, win: float = WINDOW_SECONDS) -> list[float]:
    """Offset (secondi) di 3 finestre a ~10%/50%/85% della traccia — così misuro
    l'energia della TRACCIA, non solo dell'intro. Traccia corta/sconosciuta -> una
    finestra dall'inizio."""
    if not duration or duration <= win:
        return [0.0]
    last = duration - win
    offs = {round(min(last, max(0.0, duration * f)), 3) for f in (0.10, 0.50, 0.85)}
    return sorted(offs)


def analyze_file(path, duration_seconds: float | None = None) -> float | None:
    """`energy_raw` (0..1) di un file, mediando le feature su 3 finestre. None se il
    file non è decodificabile. Non riproduce né muta il file: solo lettura."""
    from app.integrations.local_files import LocalFilesError, decode_pcm_bytes

    feats: list[tuple[float, float, float]] = []
    for offset in _window_offsets(duration_seconds):
        try:
            raw = decode_pcm_bytes(path, offset=offset, seconds=WINDOW_SECONDS)
        except LocalFilesError:
            continue
        samples = np.frombuffer(raw, dtype=np.int16)
        if samples.size:
            feats.append(pcm_features(samples))
    if not feats:
        return None
    rms = float(np.mean([f[0] for f in feats]))
    centroid = float(np.mean([f[1] for f in feats]))
    flux = float(np.max([f[2] for f in feats]))  # il picco di transienti descrive la traccia
    return combine_features(rms, centroid, flux)


def percentile_ranks(values: list[float]) -> list[int]:
    """Rango percentile (0-100) di ciascun valore nella distribuzione. Una sola
    traccia -> 50 (a metà). Calibrare così rende "100" la traccia più energica
    della TUA libreria, non un ideale assoluto (l'RMS dipende dal mastering)."""
    n = len(values)
    if n == 0:
        return []
    arr = np.asarray(values, dtype=np.float64)
    out = []
    for v in arr:
        pct = (np.sum(arr < v) + 0.5 * np.sum(arr == v)) / n
        out.append(int(round(pct * 100)))
    return out


def backfill_energy(db, *, analyzer=None, limit: int | None = None) -> int:
    """Analizza i file posseduti senza `energy_raw` (backfill una-tantum sui brani
    già indicizzati, che la passata incrementale salterebbe). Resumable: riparte da
    dove si era fermato. Ricalibra a fine giro. Ritorna quanti file ha analizzato."""
    from sqlalchemy import select

    from app.models import Track

    run = analyzer or analyze_file
    query = select(Track).where(
        Track.has_local_file.is_(True),
        Track.local_path.isnot(None),
        Track.energy_raw.is_(None),
    )
    if limit:
        query = query.limit(limit)
    done = 0
    for track in db.scalars(query).all():
        try:
            raw = run(track.local_path, track.duration_seconds)
        except Exception:
            raw = None
        if raw is not None:
            track.energy_raw = raw
            done += 1
    db.commit()
    recompute_energy(db)
    return done


def recompute_energy(db) -> int:
    """Ricalibra `energy` (0-100) per percentili su tutte le tracce con `energy_raw`.
    Lascia intatte quelle senza feature calcolate (lead senza file: restano col proxy).
    Ritorna il numero di tracce aggiornate."""
    from sqlalchemy import select

    from app.models import Track

    tracks = db.scalars(select(Track).where(Track.energy_raw.isnot(None))).all()
    if not tracks:
        return 0
    for track, energy in zip(tracks, percentile_ranks([t.energy_raw for t in tracks])):
        track.energy = energy
        track.energy_source = "computed"
    db.commit()
    return len(tracks)
