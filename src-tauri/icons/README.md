# Icona Cratory

La sorgente condivisa da browser e bundle desktop è
[`frontend/app/icon.svg`](../../frontend/app/icon.svg): C Corrosione approvata,
chiara `#ededed` su fondo `#0d0d0d`. Il simbolo occupa circa il 65% dell'altezza
ed è centrato sul proprio ingombro visibile.

L'SVG incorpora in base64, senza ridisegnarlo, il PNG trasparente approvato
(1254 × 1254 RGBA) usato come maschera alpha: il disegno vive dentro l'SVG e
non in una cartella di lavoro esterna. Per rigenerare le icone basta questo
file. La stessa maschera, esportata a 24 px per la barra laterale, è in
[`frontend/public/brand/cratory-mark.png`](../../frontend/public/brand/cratory-mark.png).

## Rigenerazione

Dalla radice del repository, con le dipendenze frontend già installate:

```sh
CRATORY_ICON_TMP="$(mktemp -d)"
./frontend/node_modules/.bin/tauri icon frontend/app/icon.svg --output "$CRATORY_ICON_TMP"
for icon in src-tauri/icons/*.png src-tauri/icons/*.icns src-tauri/icons/*.ico; do
  cp "$CRATORY_ICON_TMP/$(basename "$icon")" "$icon"
done
```

La CLI genera anche file mobile nella cartella temporanea: vengono copiati
solo i formati desktop già presenti. I PNG devono restare RGBA, anche con
fondo completamente opaco: Tauri non accetta RGB per l'icona incorporata.

Il bundle usa PNG 32, 128 e 256 px, ICNS e ICO; `icon.png` è il master
esportato a 512 px. Gli altri PNG sono i formati Windows mantenuti nel set.
