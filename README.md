# DjOrganizer

Tool personale, locale e standalone per organizzare le cartelle di musica sul disco e
prepararle all'import in **Rekordbox**: pulizia tag/metadata, rinomina file e struttura
cartelle, deduplica e quality check.

Non riproduce audio, non conserva audio e **non analizza BPM/key** (quello lo fa
Rekordbox).

App separata da **Cratory**, con cui condivide il design system. Può collegarsi in sola
lettura all'API di Cratory per proporre genere/label/anno gia' arricchiti, ma funziona
al 100% anche da sola.

## Stato

Operativo: pipeline completa scan → issues → dedup → piano → applica → undo,
testata end-to-end (176 test). Il bridge read-only verso Cratory suggerisce
genere/etichetta/anno durante la pulizia dei tag (opzionale: senza Cratory
l'app funziona identica).

## Posto nella catena

`inbox/` → **DjOrganizer** → `Libreria/{genere}/{artist}/Artist - Title.ext` → Rekordbox.
Unico scrittore dei tag dell'ecosistema; precedenza valori:
manuale > tag pulito del file > suggerimento Cratory > AI dal nome file.
Vedi `~/Develop/dj-ecosystem-north-star.md`.

## Principio di sicurezza

Ogni operazione sui file e' prima un **piano** che approvi. Le modifiche sono in-place
ma reversibili: i delete vanno in **quarantena** (mai hard-delete) e ogni run scrive un
**undo journal** per annullare tutto.
