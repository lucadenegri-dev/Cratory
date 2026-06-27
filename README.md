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

In design. La specifica corrente:
[docs/superpowers/specs/2026-06-27-djorganizer-design.md](docs/superpowers/specs/2026-06-27-djorganizer-design.md).

## Principio di sicurezza

Ogni operazione sui file e' prima un **piano** che approvi. Le modifiche sono in-place
ma reversibili: i delete vanno in **quarantena** (mai hard-delete) e ogni run scrive un
**undo journal** per annullare tutto.
