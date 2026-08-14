"""Dialog nativo macOS (Finder): alias di modulo verso il core.

Implementazione unica in `app.services.native_picker` (era byte-identica
qui, duplicata dalla fusione Sortory->Cratory). Non e' un semplice
re-export dei simboli: un `import` dei singoli nomi (`from ... import
pick_path`) legherebbe qui una funzione i cui lookup di globals restano
comunque quelli del modulo core, rompendo i test che monkeypatchano
`picker_available` (o il lock privato `_lock`) passando da QUESTO modulo —
`pick_path` continuerebbe a vedere l'originale non patchato. La riga sotto
sostituisce invece l'intera voce di `sys.modules` per questo nome con il
modulo core: dopo l'esecuzione, `app.organize.services.native_picker` e'
letteralmente lo stesso oggetto modulo di `app.services.native_picker` (un
solo `_lock`, un solo dict di globals), quindi qualunque test che
monkeypatcha via l'uno o l'altro percorso resta valido. `organize/` e' il
namespace assorbito: importa dal core, non il contrario.
"""
from __future__ import annotations

import sys

from app.services import native_picker as _native_picker

sys.modules[__name__] = _native_picker
