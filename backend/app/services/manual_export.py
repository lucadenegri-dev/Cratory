"""Export del set manuale (tappa 5).

Un solo renderer per formato, che l'anteprima e il download chiamano allo stesso
modo: l'anteprima e' la stessa risposta dell'endpoint, quindi «l'anteprima
coincide con cio' che esporto» e' vero per costruzione e non per disciplina.

Tutto legge il PERCORSO RISOLTO (`manual_set.resolved_path`): banco, riserva e
alternative non sono il set. Le due eccezioni sono dichiarate: la scheda di
preparazione mostra anche alternative e varchi, perche' servono in cabina, e
l'export "reserve" e' fatto apposta per la riserva.
"""

from __future__ import annotations

import csv
import io

from app.models import Setlist
from app.services.export_render import fmt_duration, render_m3u8
from app.services.manual_pairs import bpm_of, pair_compat
from app.services.manual_set import (
    blocks_of, pair_note_map, path_rows, reserve_rows, resolved_path, set_duration,
)

MANUAL_FORMATS = ("text", "csv", "markdown", "m3u8", "prep", "reserve")

_IGNOTO = "—"


def _label(track) -> str:
    return f"{track.artist or '?'} - {track.title or '?'}"


def _render_text(setlist: Setlist, lang: str) -> str:
    righe = [f"# {setlist.name}", ""]
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        tempo = bpm_of(row)
        meta = f"[{tempo:.0f} BPM, {t.camelot_key or '?'}]" if tempo else f"[{t.camelot_key or '?'}]"
        righe.append(f"{i:2d}. {_label(t)} {meta}")
    return "\n".join(righe)


def _render_csv(setlist: Setlist, lang: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["position", "title", "artist", "bpm", "play_bpm", "key",
                "duration_seconds", "planned_seconds", "note", "local_path"])
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        w.writerow([i, t.title or "", t.artist or "", t.bpm or "", row.play_bpm or "",
                    t.camelot_key or "", t.duration_seconds or "", row.planned_seconds or "",
                    row.note or "", t.local_path or ""])
    return buf.getvalue()


def _render_markdown(setlist: Setlist, lang: str) -> str:
    md = [f"# {setlist.name}", "",
          "| # | Traccia | BPM | Key | Durata |", "|--:|---|--:|---|--:|"]
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        tempo = bpm_of(row)
        durata = fmt_duration(row.planned_seconds or t.duration_seconds)
        md.append(f"| {i} | {_label(t)} | {tempo:.0f} | {t.camelot_key or '?'} | {durata} |"
                  if tempo else
                  f"| {i} | {_label(t)} | {_IGNOTO} | {t.camelot_key or '?'} | {durata} |")
    return "\n".join(md)


def _render_m3u8(setlist: Setlist, lang: str) -> str:
    righe = resolved_path(setlist)
    posseduti = [r.track for r in righe if r.track.local_path]
    return render_m3u8(posseduti, len(righe))


def _render_prep(setlist: Setlist, lang: str) -> str:
    """La scheda che il DJ si porta in cabina: sequenze, appunti, alternative,
    varchi e passaggi. Una traccia senza file resta e si dichiara — e' una
    decisione presa, e nasconderla sarebbe una bugia."""
    d = set_duration(setlist)
    md = [f"# {setlist.name}", ""]
    md.append(f"{len(resolved_path(setlist))} tracce · {fmt_duration(d.seconds)}"
              + (" (stima incompleta)" if d.incomplete else ""))
    md.append("")

    note_coppie = pair_note_map(setlist)
    precedente = None
    for block in blocks_of(setlist, "main"):
        md += [f"## {block.name or 'senza nome'}", ""]
        for row in sorted(block.rows, key=lambda r: r.position):
            if row.track is None:
                md.append("- **[varco]** " + (row.note or ""))
                precedente = None
                continue
            t = row.track
            tempo = bpm_of(row)
            pezzi = [f"{tempo:.0f} BPM" if tempo else _IGNOTO, t.camelot_key or _IGNOTO]
            if row.play_bpm:
                pezzi.append(f"la suono a {row.play_bpm:.0f}")
            if not t.has_local_file:
                pezzi.append("non disponibile")
            md.append(f"- **{_label(t)}** — {' · '.join(pezzi)}")
            if precedente is not None:
                c = pair_compat(precedente, row)
                passaggio = (f"{c.bpm_percent:+.1f} %" if c.bpm_percent is not None else _IGNOTO)
                appunto = note_coppie.get((precedente.track_id, row.track_id))
                md.append(f"  - passaggio: pitch {passaggio}"
                          + (f" — {appunto}" if appunto else ""))
            if row.note:
                md.append(f"  - appunto: {row.note}")
            for alt in sorted(row.alternatives, key=lambda a: a.position):
                md.append(f"  - alternativa: {_label(alt.track)}")
            precedente = row
        md.append("")

    banco = blocks_of(setlist, "bench")
    if banco:
        md += ["## Banco", ""]
        for block in banco:
            md.append(f"- **{block.name or 'senza nome'}**: "
                      + ", ".join(_label(r.track) for r in block.rows if r.track))
        md.append("")

    riserva = reserve_rows(setlist)
    if riserva:
        md += ["## Riserva", ""]
        md += [f"- {_label(r.track)}" for r in riserva if r.track]
    return "\n".join(md)


def _render_reserve(setlist: Setlist, lang: str) -> str:
    righe = [f"# {setlist.name} — riserva", ""]
    for row in reserve_rows(setlist):
        if row.track is None:
            continue
        t = row.track
        meta = f"[{t.bpm:.0f} BPM, {t.camelot_key or '?'}]" if t.bpm else f"[{t.camelot_key or '?'}]"
        righe.append(f"- {_label(t)} {meta}")
    return "\n".join(righe)


_RENDERERS = {
    "text": (_render_text, "text/plain"),
    "csv": (_render_csv, "text/csv"),
    "markdown": (_render_markdown, "text/markdown"),
    "m3u8": (_render_m3u8, "audio/x-mpegurl"),
    "prep": (_render_prep, "text/markdown"),
    "reserve": (_render_reserve, "text/markdown"),
}


def render_manual(setlist: Setlist, fmt: str, lang: str) -> tuple[str, str]:
    render, media = _RENDERERS[fmt]
    return render(setlist, lang), media
