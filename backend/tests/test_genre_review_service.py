"""Test del service di revisione generi (Task 1: colonna; Task 4: logica)."""

from app.models import AudioFile


def _file(db, fid, *, artist=None, title=None, genre=None, album=None,
          label=None, reviewed=None, path=None):
    f = AudioFile(id=fid, root_id=1, path=path or f"/m/{fid}.mp3", ext="mp3",
                  size_bytes=1, hash_method="file", status="present",
                  has_cover=False, artist=artist, title=title, genre=genre,
                  album=album, label=label, genre_reviewed_at=reviewed)
    db.add(f)
    db.commit()
    return f


def test_genre_reviewed_at_column_defaults_none(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties")
    assert f.genre_reviewed_at is None


from sqlalchemy import select

from app.models import Issue
from app.services import genre_review


class _MB:
    """MusicBrainz finto: risponde con candidati fissi (o None)."""
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def lookup(self, **kw):
        self.calls.append(kw)
        return self.result


class _DG:
    """Discogs finto: risponde con candidati fissi (o None), registra le chiamate
    (serve a verificare che venga interrogato solo come gap-fill, Finding 5)."""
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def lookup(self, **kw):
        self.calls.append(kw)
        return self.result


def _ai_returning(*proposals):
    """ai_fn finto: risponde con le proposte date, allineate all'input.
    Accetta (e ignora) max_web_searches/always_search: i test che verificano
    quei parametri usano una fake dedicata (_ai_capturing)."""
    def fn(items, **kwargs):
        assert len(items) == len(proposals)
        return list(proposals)
    return fn


def _ai_capturing(calls, *, genre=None, confidence="low"):
    """ai_fn finto che registra ogni chiamata (items, kwargs) in `calls` e
    risponde con un esito fisso per ogni item — serve a ispezionare come
    review() partiziona i sotto-batch e con quale budget/modalità li chiama."""
    def fn(items, **kwargs):
        calls.append((list(items), dict(kwargs)))
        return [{"genre": genre, "confidence": confidence} for _ in items]
    return fn


def _issues(db, fid):
    return db.scalars(select(Issue).where(Issue.file_id == fid)).all()


def test_count_candidates_skips_reviewed_unless_redo(db):
    from app.models import utcnow
    _file(db, 1, artist="A", title="T1")
    _file(db, 2, artist="B", title="T2", reviewed=utcnow())
    assert genre_review.count_candidates(db) == 1
    assert genre_review.count_candidates(db, redo=True) == 2


def test_review_proposes_genre_review_issue_when_differs(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties", genre="House")
    res = genre_review.review(
        db, mb=_MB({"genre_candidates": ["Techno"]}), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["proposed"] == 1 and res["confirmed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.type == "genre_review" and issue.field == "genre"
    assert issue.status == "open"
    assert issue.suggested_fix_json == {
        "field": "genre", "action": "retag", "to": "Techno",
        "source": "ai", "confidence": "high", "level": None}
    assert f.genre_reviewed_at is not None


def test_review_proposal_detail_and_fix_carry_level(db):
    """Il livello di evidenza (track/release/artist) arriva sia nel detail
    mostrato in ISSUES sia nel suggested_fix_json, così l'utente vede a
    colpo d'occhio se la proposta nasce da un tag di traccia o solo dalla
    fama generale dell'artista."""
    _file(db, 1, artist="Oneohtrix Point Never", title="Boring Angel",
          genre="Ambient")
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Progressive Electronic",
                             "confidence": "high", "level": "release"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)
    assert issue.detail == "AI (release): genre → Progressive Electronic"
    assert issue.suggested_fix_json == {
        "field": "genre", "action": "retag", "to": "Progressive Electronic",
        "source": "ai", "confidence": "high", "level": "release"}


def test_review_proposal_detail_without_level_has_no_parentheses(db):
    """Una proposta senza livello (None, es. modello che non lo valorizza)
    produce un detail senza parentesi, invece di 'AI (None): ...'."""
    f = _file(db, 1, artist="A", title="T", genre="House")
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)
    assert issue.detail == "AI: genre → Techno"
    assert "level" in issue.suggested_fix_json
    assert issue.suggested_fix_json["level"] is None
    assert f.genre_reviewed_at is not None


def test_review_confirm_same_genre_no_issue_and_closes_stale(db):
    _file(db, 1, artist="A", title="T", genre="tech house")  # casing diverso
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="vecchia proposta", status="open",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Tech House", "confidence": "high"}))
    assert res["confirmed"] == 1 and res["proposed"] == 0
    assert _issues(db, 1) == []  # la genre_review aperta e ora inutile sparisce


def test_review_fills_open_missing_metadata_issue(db):
    _file(db, 1, artist="A", title="T", genre=None)
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Dub Techno", "confidence": "low"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)  # nessuna issue duplicata
    assert issue.type == "missing_metadata"
    assert issue.suggested_fix_json["to"] == "Dub Techno"
    assert issue.suggested_fix_json["source"] == "ai"


def test_review_never_overwrites_provider_suggestion(db):
    _file(db, 1, artist="A", title="T", genre=None)
    provider_fix = {"field": "genre", "action": "retag", "to": "House",
                    "source": "provider", "confidence": "high"}
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=provider_fix, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1 and res["proposed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.suggested_fix_json == provider_fix  # intatto


def test_review_skips_when_provider_override_open(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="provider_override", field="genre",
                 severity="info", detail="provider: genre → Techno",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "provider",
                                     "confidence": "strong"}, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Minimal", "confidence": "low"}))
    assert res["skipped"] == 1
    assert len(_issues(db, 1)) == 1  # nessuna seconda issue sul campo genre


def test_review_none_is_unresolved_but_marks_reviewed(db):
    f = _file(db, 1, artist="A", title="T", genre="House")
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}))
    assert res["unresolved"] == 1
    assert _issues(db, 1) == []
    assert f.genre_reviewed_at is not None


def test_review_respects_user_decision_on_genre_review(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", status="dismissed",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1
    (issue,) = _issues(db, 1)
    assert issue.status == "dismissed"  # decisione utente intoccata


def test_review_ai_failure_counts_unresolved_and_continues(db):
    # Finding 4: un batch il cui ai_fn solleva non deve marcare
    # genre_reviewed_at sui suoi file — restano candidati per la passata
    # successiva invece di risultare "revisionati senza proposte" (chiave
    # invalida/quota esaurita/server tool disabilitato sono transitori).
    f1 = _file(db, 1, artist="A", title="T")
    f2 = _file(db, 2, artist="B", title="U")

    def boom(items, **kwargs):
        raise RuntimeError("api down")

    res = genre_review.review(db, mb=_MB(None), discogs=_DG(None), ai_fn=boom)
    assert res["unresolved"] == 2
    assert res["files"] == 2
    assert f1.genre_reviewed_at is None
    assert f2.genre_reviewed_at is None


def test_review_candidates_merged_normalized_deduped(db):
    # MB vuoto → Discogs fa gap-fill: i suoi candidati arrivano comunque,
    # normalizzati e deduplicati.
    _file(db, 1, artist="A", title="T")
    captured = {}

    def fn(items, **kwargs):
        captured["items"] = items
        return [{"genre": None, "confidence": "low"}]

    genre_review.review(
        db,
        mb=_MB(None),
        discogs=_DG({"genre_candidates": ["Tech House", "tech house", "Electronic"]}),
        ai_fn=fn)
    assert captured["items"][0]["candidates"] == ["Tech House", "Electronic"]


def test_review_candidates_skip_discogs_when_mb_has_candidates(db):
    """Finding 5: Discogs si interroga solo come gap-fill. Se MusicBrainz ha
    già dato candidati, il finto Discogs non deve essere chiamato — senza
    token il suo limite è ~25 richieste/minuto, interrogarlo sempre sprecherebbe
    la maggior parte delle chiamate in 429."""
    _file(db, 1, artist="A", title="T")
    captured = {}
    dg = _DG({"genre_candidates": ["Electronic"]})

    def fn(items, **kwargs):
        captured["items"] = items
        return [{"genre": None, "confidence": "low"}]

    genre_review.review(
        db,
        mb=_MB({"genre_candidates": ["tech house", "techno"],
                "genre_primary": "tech house"}),
        discogs=dg, ai_fn=fn)
    assert dg.calls == []
    assert captured["items"][0]["candidates"] == ["Tech House", "Techno"]


def test_review_candidates_calls_discogs_when_mb_empty(db):
    """Finding 5, gemello: quando MusicBrainz non produce nulla, Discogs viene
    interrogato (gap-fill)."""
    _file(db, 1, artist="A", title="T")
    dg = _DG({"genre_candidates": ["Electronic"]})

    def fn(items, **kwargs):
        return [{"genre": None, "confidence": "low"}]

    genre_review.review(db, mb=_MB(None), discogs=dg, ai_fn=fn)
    assert len(dg.calls) == 1


def test_review_progress_phases(db):
    _file(db, 1, artist="A", title="T")
    seen = []
    genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}),
        on_progress=lambda p, t, ph: seen.append((p, t, ph)))
    assert ("looking_up" in {ph for _, _, ph in seen})
    assert seen[-1] == (1, 1, "reviewing")


def test_review_fills_missing_metadata_and_drops_stale_open_genre_review(db):
    """Finding 1: una genre_review aperta rimasta da una passata precedente
    va eliminata quando una missing_metadata aperta sullo stesso campo viene
    riempita dalla nuova proposta AI — non devono restare due issue aperte
    sullo stesso file/campo."""
    _file(db, 1, artist="A", title="T", genre=None)
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="vecchia proposta AI", status="open",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Dub Techno", "confidence": "low"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)  # la genre_review stantia è sparita
    assert issue.type == "missing_metadata"
    assert issue.suggested_fix_json["to"] == "Dub Techno"
    assert issue.suggested_fix_json["source"] == "ai"


def test_review_fills_missing_metadata_keeps_dismissed_genre_review(db):
    """Una genre_review già decisa dall'utente (dismissed) non va mai toccata,
    nemmeno quando esiste anche una missing_metadata aperta sullo stesso
    campo che la proposta AI riempie."""
    _file(db, 1, artist="A", title="T", genre=None)
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", status="dismissed",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Dub Techno", "confidence": "low"}))
    assert res["proposed"] == 1
    issues = {i.type: i for i in _issues(db, 1)}
    assert set(issues) == {"genre_review", "missing_metadata"}
    assert issues["genre_review"].status == "dismissed"  # decisione utente intoccata
    assert issues["missing_metadata"].suggested_fix_json["to"] == "Dub Techno"


def test_review_drops_stale_genre_review_when_other_open_issue_on_field(db):
    """Finding 6: copre il terzo call site di _drop_stale_review_row (ramo
    'un'altra issue aperta sul campo', diverso da fillable/confirmed). Un file
    con una genre_review aperta *e* una provider_override aperta sul campo
    genre: dopo review() la genre_review stantia sparisce, la
    provider_override resta intatta (provider > AI, mai sovrascritta)."""
    _file(db, 1, artist="A", title="T", genre="House")
    override_fix = {"field": "genre", "action": "retag", "to": "Techno",
                    "source": "provider", "confidence": "strong"}
    db.add(Issue(file_id=1, type="provider_override", field="genre",
                 severity="info", detail="provider: genre → Techno",
                 suggested_fix_json=override_fix, status="open"))
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="vecchia proposta AI", status="open",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Minimal", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Minimal", "confidence": "low"}))
    assert res["skipped"] == 1
    (issue,) = _issues(db, 1)  # la genre_review stantia è sparita
    assert issue.type == "provider_override"
    assert issue.suggested_fix_json == override_fix  # intatta
    assert issue.status == "open"


def test_review_batches_respect_batch_size(db):
    """Finding 2: review() deve spezzare le richieste AI in slice non più
    grandi di batch_size, chiamando ai_fn una volta per slice. Qui tutti i
    file sono privi di candidati (bisognosi): un'unica partizione più grande
    di batch_size."""
    for i in range(1, 6):
        _file(db, i, artist=f"A{i}", title=f"T{i}", genre="House")
    call_sizes = []

    def fn(items, **kwargs):
        call_sizes.append(len(items))
        return [{"genre": None, "confidence": "low"} for _ in items]

    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None), ai_fn=fn, batch_size=2)
    assert len(call_sizes) == 3  # 2 + 2 + 1
    assert all(n <= 2 for n in call_sizes)
    assert sum(call_sizes) == 5
    assert res["files"] == 5
    assert res["unresolved"] == 5


def test_review_covered_partition_also_respects_batch_size(db):
    """Simmetrico al test precedente ma per la partizione coperta (tutte le
    tracce hanno candidati dal provider): nessun sotto-batch supera
    batch_size, anche se la partizione coperta è più grande di batch_size."""
    for i in range(1, 6):
        _file(db, i, artist=f"A{i}", title=f"T{i}", genre="House")
    call_sizes = []

    def fn(items, **kwargs):
        call_sizes.append(len(items))
        return [{"genre": None, "confidence": "low"} for _ in items]

    res = genre_review.review(
        db, mb=_MB({"genre_candidates": ["Techno"]}), discogs=_DG(None),
        ai_fn=fn, batch_size=2)
    assert len(call_sizes) == 3  # 2 + 2 + 1
    assert all(n <= 2 for n in call_sizes)
    assert sum(call_sizes) == 5
    assert res["files"] == 5


def test_review_window_mixed_partition_two_distinct_ai_calls(db):
    """Una finestra con tracce coperte (candidati dai provider) e bisognose
    (nessun candidato) produce due chiamate ai_fn distinte: quella delle
    tracce senza candidati ha budget pari al numero di tracce del sotto-batch
    e modalità 'cerca sempre'; quella delle tracce coperte ha budget basso e
    NON richiede la ricerca."""
    _file(db, 1, artist="A1", title="T1", genre="House")  # coperto
    _file(db, 2, artist="A2", title="T2", genre="House")  # coperto
    _file(db, 3, artist="A3", title="T3", genre="House")  # coperto
    _file(db, 4, artist="A4", title="T4", genre="House")  # bisognoso

    class _MixedMB:
        def lookup(self, **kw):
            if kw.get("artist") in ("A1", "A2", "A3"):
                return {"genre_candidates": ["Techno"]}
            return None

    calls = []
    res = genre_review.review(
        db, mb=_MixedMB(), discogs=_DG(None),
        ai_fn=_ai_capturing(calls))

    assert len(calls) == 2
    needy_items, needy_kwargs = next(
        c for c in calls if c[1]["always_search"] is True)
    covered_items, covered_kwargs = next(
        c for c in calls if c[1]["always_search"] is False)
    assert len(needy_items) == 1  # solo A4
    assert needy_kwargs["max_web_searches"] == 1  # una ricerca a testa
    assert len(covered_items) == 3  # A1, A2, A3
    # budget basso e NON proporzionale al numero di tracce coperte (3):
    # è un tetto fisso, non "una a testa" come per i bisognosi.
    assert covered_kwargs["max_web_searches"] < len(covered_items)
    assert res["files"] == 4


def test_review_window_all_needy_no_call_for_empty_covered_partition(db):
    """Una finestra di sole tracce bisognose non produce nessuna chiamata
    ai_fn per la partizione coperta, che è vuota."""
    _file(db, 1, artist="A", title="T", genre="House")
    _file(db, 2, artist="B", title="U", genre="House")
    calls = []
    genre_review.review(
        db, mb=_MB(None), discogs=_DG(None), ai_fn=_ai_capturing(calls))
    assert len(calls) == 1
    assert calls[0][1]["always_search"] is True
    assert len(calls[0][0]) == 2


def test_review_window_all_covered_no_call_for_empty_needy_partition(db):
    """Simmetrico: una finestra di sole tracce coperte non produce nessuna
    chiamata ai_fn per la partizione bisognosa, che è vuota."""
    _file(db, 1, artist="A", title="T", genre="House")
    _file(db, 2, artist="B", title="U", genre="House")
    calls = []
    genre_review.review(
        db, mb=_MB({"genre_candidates": ["Techno"]}), discogs=_DG(None),
        ai_fn=_ai_capturing(calls))
    assert len(calls) == 1
    assert calls[0][1]["always_search"] is False
    assert len(calls[0][0]) == 2


def test_review_needy_partition_failure_does_not_block_covered(db):
    """Il fallimento della chiamata AI su una partizione (qui: la bisognosa)
    non impedisce all'altra partizione (coperta) di essere processata, e
    lascia non marcati solo i file della partizione fallita."""
    f1 = _file(db, 1, artist="A1", title="T1", genre="House")  # coperto
    f2 = _file(db, 2, artist="A2", title="T2", genre="House")  # bisognoso

    class _MixedMB:
        def lookup(self, **kw):
            if kw.get("artist") == "A1":
                return {"genre_candidates": ["Techno"]}
            return None

    def fn(items, *, always_search, **kwargs):
        if always_search:
            raise RuntimeError("web search down")
        return [{"genre": None, "confidence": "low"} for _ in items]

    res = genre_review.review(
        db, mb=_MixedMB(), discogs=_DG(None), ai_fn=fn)
    assert res["unresolved"] == 2  # covered: genre None -> unresolved; needy: fallito -> unresolved
    assert f1.genre_reviewed_at is not None  # partizione coperta processata
    assert f2.genre_reviewed_at is None  # partizione bisognosa fallita: non marcato
