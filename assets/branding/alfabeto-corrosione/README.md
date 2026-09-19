# Alfabeto Corrosione — Cratory

26 lettere maiuscole A–Z nello stile della C del marchio Cratory.

- [Tavola completa con etichette](alfabeto-az.png)
- [PNG trasparente senza etichette](alfabeto-az-trasparente.png)
- [26 lettere SVG separate, da A.svg a Z.svg](svg/)
- [Tavola completa SVG trasparente](alfabeto-az.svg)
- [Prompt e dettagli di generazione](PROMPTS.md)

Entrambe le tavole misurano 1536 × 1024 pixel. Le lettere sono disposte così:

```text
A B C D E F G
H I J K L M N
O P Q R S T U
V W X Y Z
```

## Versione vettoriale

La cartella `svg/` contiene 26 file separati, da `A.svg` a `Z.svg`, con
tracciati Bézier modificabili, sfondo trasparente e vuoti interni conservati.
Ogni lettera ha un `viewBox` ritagliato con 12 unità di margine. Le dimensioni
mantengono le proporzioni della tavola originale; non sono normalizzate a una
larghezza comune.

`alfabeto-az.svg` raccoglie gli stessi tracciati nella disposizione originale
1536 × 1024, senza etichette, con gruppi identificati da `letter-A` a `letter-Z`.
Nessun SVG contiene immagini raster incorporate o dipende da font esterni.

Il colore predefinito è nero (`fill="currentColor"`). Per cambiarlo in un editor
vettoriale, modifica il riempimento; nell'SVG inline puoi impostare la proprietà
CSS `color`, per esempio `#ededed` sul fondo scuro o `#15140f` sul fondo carta.
Un SVG caricato tramite `<img>` non eredita il colore CSS della pagina.

I contorni sono vettorializzati dalla maschera alpha del PNG trasparente
(soglia 128, Potrace, tolleranza curve 0.15), con texture raster rimossa.
Sono asset grafici, non un font installabile.

## I singoli SVG

`svg/A.svg` … `svg/Z.svg` sono le stesse lettere in vettoriale, una per file,
con `fill="currentColor"` e `fill-rule="evenodd"`. Il viewBox di ciascuna è il
rettangolo d'inchiostro della lettera più 12 unità di margine per lato.

Due cose vanno rispettate da chiunque le usi, perché senza si rompono in
silenzio:

- **`fill-rule="evenodd"`**: è ciò che tiene vuoti gli occhielli. Perderla per
  strada riempie la pancia della O e la lettera diventa un rombo nero.
- **nessun colore scritto nel tracciato**: il colore arriva da `currentColor`,
  ed è così che la scritta vive sia sul tema scuro sia su carta.

Le lettere non sono allineate fra loro: la tavola è un campionario, quindi sono
allineate in cima e alte quanto capita (in una banda i fondi variano fino a 30
px). Chi compone una parola deve portarle lui a un'altezza comune e a una linea
di base comune — sempre con una scala **uniforme**, mai stirando in altezza.

## Da qui all'applicazione

La Home usa solo le undici lettere che le servono (CRATORY, più DJ GOODGIRL per
l'easter egg). Il dizionario dei glifi è generato, non scritto a mano:

```sh
python3 assets/branding/alfabeto-corrosione/genera-glifi.py \
    > frontend/components/dashboard/logo-glyphs.ts
```

Lo script si ferma con un errore se una lettera non dichiara la `fill-rule` o
se le lettere non la dichiarano tutte uguale: meglio una generazione fallita di
una O piena scoperta a schermo. A comporre la parola pensa
`frontend/components/dashboard/logo-wordmark.tsx`.
