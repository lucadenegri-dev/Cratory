"""Selezione deterministica del candidato Soulseek (zero AI).

Ordina i file restituiti da slskd per aderenza ad artista+titolo e qualita',
secondo una preferenza configurabile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.integrations.slskd import SlskdFile

_SPACE_RE = re.compile(r"\s+")
LOSSLESS_EXTS = {"flac", "wav", "aiff", "aif", "alac", "ape"}
LOSSY_EXTS = {"mp3", "m4a", "aac", "ogg", "opus", "wma"}

AUTO_PICK_MIN_CONFIDENCE = 0.7
_MIN_NAME_SCORE = 0.45

# Token di versione: per un DJ il radio edit al posto dell'extended e' un fallimento
# silenzioso, quindi si confrontano esplicitamente. "original" e "mix" sono esclusi
# di proposito: "Original Mix" e' la versione di default (= nessun token).
_VERSION_TOKENS = {
    "remix", "extended", "edit", "radio", "live", "instrumental", "acoustic",
    "dub", "vip", "rework", "bootleg", "mashup", "acapella", "club",
}

# Pulizia progressiva della query (Soulseek fa match AND sui token: quelli
# accessori del titolo Spotify escludono file validi nominati diversamente).
_PARENS_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
_VERSION_SUFFIX_RE = re.compile(
    r"\s+-\s+[^-]*\b(?:extended|remix|edit|mix|version|radio|live|dub|"
    r"instrumental|rework|remaster(?:ed)?)\b[^-]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QualityPreference:
    prefer_lossless: bool = True
    min_bitrate: int = 256
    preferred_bitrate: int = 320


@dataclass
class ScoredCandidate:
    file: SlskdFile
    name_score: float
    quality_tier: int
    score: float
    confidence: float


def _norm(text: str | None) -> str:
    text = (text or "").lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _strip_extension(filename: str) -> str:
    if "." in filename:
        return filename.rsplit(".", 1)[0]
    return filename


def _basename_stem(filename: str) -> str:
    """Solo il nome file (senza cartelle ne' estensione).

    I path Soulseek sono lunghi e rumorosi (`Music\\Arca\\KiCk i (2020) [FLAC]\\02 Time.flac`):
    il titolo va confrontato col nome file, non con l'intero path, altrimenti il
    rumore di cartelle/anno/formato abbatte la similarita'.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return _strip_extension(name)


def _version_tokens(text_norm: str) -> set[str]:
    return set(text_norm.split()) & _VERSION_TOKENS


def _name_score(file: SlskdFile, artist: str, title: str) -> float:
    full = _norm(file.filename.replace("\\", "/").replace("/", " "))
    base = _norm(_basename_stem(file.filename))
    a, t_full = _norm(artist), _norm(title)
    # Similarita' sul NUCLEO del titolo: parentesi/feat/suffissi sono rumore che nei
    # nomi file non compare quasi mai. Le versioni si confrontano a parte, dal
    # titolo completo (vivono proprio nelle parentesi).
    t = _norm(_clean_title(title)) or t_full
    s = 0.0
    if t:
        # Titolo: confronto col nome file (alto segnale) + bonus se contenuto.
        s += SequenceMatcher(None, t, base).ratio() * 0.55
        if t in base:
            s += 0.30
        elif t in full:
            s += 0.15
    if a:
        # Artista: di solito e' una cartella del path → cerca nell'intero path.
        if a in full:
            s += 0.15
        else:
            s += SequenceMatcher(None, a, full).ratio() * 0.10
    # Versioni esplicite: la versione richiesta va premiata, quella non richiesta
    # (o mancante quando richiesta) penalizzata — la similarita' generica da sola
    # non distingue "Song (Radio Edit)" da "Song (Extended Mix)".
    wanted, got = _version_tokens(t_full), _version_tokens(base)
    if wanted & got:
        s += 0.15
    elif wanted or got:
        s -= 0.20
    return max(0.0, min(s, 1.0))


def _duration_score(file_length: int | None, expected: int | None) -> float:
    """Aderenza alla durata attesa: il discriminatore piu' forte tra versioni.

    Ignota (uno dei due None) → 0: Soulseek spesso non riporta la durata e
    l'ignoto non va mai penalizzato.
    """
    if not file_length or not expected:
        return 0.0
    delta = abs(file_length - expected)
    if delta <= 3:
        return 1.0
    if delta <= 10:
        return 0.5
    if delta <= 20:
        return 0.0
    return -1.0


def _availability(file: SlskdFile) -> float:
    """Quanto e' probabile che l'utente ci serva il file: 1.0 = slot libero e coda
    vuota; scende con la coda; bassa senza slot libero.

    Un file da un utente senza slot o con coda lunga spesso resta "Queued, Remotely"
    e non viene mai servito: a parita' di traccia va preferito chi ci serve davvero.
    """
    if not file.has_free_slot:
        return 0.3
    q = file.queue_length or 0
    if q <= 0:
        return 1.0
    return max(0.5, 1.0 - min(q, 25) / 50.0)


def _quality_tier(file: SlskdFile, pref: QualityPreference) -> int:
    ext = file.extension
    if ext in LOSSLESS_EXTS:
        return 3
    if ext in LOSSY_EXTS:
        br = file.bitrate
        if br is None:
            # Soulseek spesso non riporta il bitrate in ricerca: ignoto != sotto-soglia.
            return 1
        if br >= pref.preferred_bitrate:
            return 2
        if br >= pref.min_bitrate:
            return 1
        return 0
    return 0


def rank_candidates(files, *, artist: str, title: str,
                    pref: QualityPreference = QualityPreference(),
                    min_name_score: float = _MIN_NAME_SCORE,
                    expected_duration: int | None = None) -> list[ScoredCandidate]:
    """Ordina i candidati. `min_name_score` filtra i match troppo deboli: per una
    ricerca manuale/libera si abbassa (0.0) perche' e' slskd ad aver gia' filtrato
    per query e l'utente sceglie a vista. `expected_duration` (secondi, dalla
    Track) premia la versione con la durata giusta e affossa quella sbagliata."""
    scored: list[ScoredCandidate] = []
    for f in files:
        tier = _quality_tier(f, pref)
        if tier == 0:
            continue
        name = _name_score(f, artist, title)
        if name < min_name_score:
            continue
        avail = _availability(f)
        dur = _duration_score(f.length, expected_duration)
        # 1 MB/s = contributo pieno; ignota = neutra.
        spd = min((f.upload_speed or 0) / 1_000_000, 1.0)
        score = name * 100 + tier * 12 + avail * 30 + dur * 35 + spd * 10
        confidence = name * 0.8 + (tier / 3) * 0.2
        if dur >= 1.0:
            confidence += 0.10  # durata esatta: quasi certamente la versione giusta
        elif dur < 0:
            confidence -= 0.25  # durata sbagliata: quasi certamente la versione sbagliata
        confidence = round(max(0.0, min(1.0, confidence)), 3)
        scored.append(ScoredCandidate(file=f, name_score=round(name, 3),
                                      quality_tier=tier, score=round(score, 2),
                                      confidence=confidence))
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def auto_pick_candidates(ranked: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Candidati eleggibili all'auto-pick: confidenza sopra soglia, ordine per
    score preservato.

    La confidenza si valuta su OGNI candidato, non solo sul primo per score:
    lo score premia anche disponibilita'/velocita', quindi un candidato piu'
    in basso ma affidabile non deve essere oscurato da un primo posto incerto.
    Lista vuota = nessun candidato affidabile → needs_review a carico del
    chiamante.
    """
    return [c for c in ranked if c.confidence >= AUTO_PICK_MIN_CONFIDENCE]


def best_for_auto(files, *, artist: str, title: str,
                  pref: QualityPreference = QualityPreference(),
                  expected_duration: int | None = None) -> ScoredCandidate | None:
    ranked = rank_candidates(files, artist=artist, title=title, pref=pref,
                             expected_duration=expected_duration)
    eligible = auto_pick_candidates(ranked)
    return eligible[0] if eligible else None


def _clean_title(title: str) -> str:
    t = _PARENS_RE.sub(" ", title or "")
    t = _FEAT_RE.sub(" ", t)
    t = _VERSION_SUFFIX_RE.sub(" ", t)
    return _SPACE_RE.sub(" ", t).strip()


def query_variants(artist: str, title: str) -> list[str]:
    """Varianti di query in ordine di fedelta': completa → pulita → essenziale.

    La pulizia riguarda SOLO la query (Soulseek fa match AND sui token): il
    ranking confronta sempre con artista/titolo originali.
    """
    variants: list[str] = []

    def add(text: str) -> None:
        text = _SPACE_RE.sub(" ", text).strip()
        if text and text not in variants:
            variants.append(text)

    add(f"{artist} {title}")
    cleaned = _clean_title(title)
    add(f"{artist} {cleaned}")
    stop = _VERSION_TOKENS | {"original", "mix"}
    core = " ".join(w for w in cleaned.split() if w.lower() not in stop)
    add(f"{artist} {core}")
    return variants


def search_candidates(client, *, artist: str, title: str,
                      expected_duration: int | None = None,
                      pref: QualityPreference = QualityPreference(),
                      min_name_score: float = _MIN_NAME_SCORE) -> list[ScoredCandidate]:
    """Cerca su slskd provando le varianti di query in cascata: si ferma alla
    prima che produce almeno un candidato valido (post-filtro)."""
    for query in query_variants(artist, title):
        files = client.search(query, "")
        ranked = rank_candidates(files, artist=artist, title=title, pref=pref,
                                 min_name_score=min_name_score,
                                 expected_duration=expected_duration)
        if ranked:
            return ranked
    return []
