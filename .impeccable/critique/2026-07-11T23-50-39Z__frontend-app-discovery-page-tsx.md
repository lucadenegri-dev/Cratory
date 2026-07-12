---
target: scheda Discovery — pannello di controllo (pre-risultati)
total_score: 27
p0_count: 0
p1_count: 1
timestamp: 2026-07-11T23-50-39Z
slug: frontend-app-discovery-page-tsx
---
# Critique — Discovery, pannello di controllo (pre-risultati)

Scope: solo il box di setup del dig (`frontend/app/discovery/page.tsx:157-289`) — seed toggle, preset profondità, affinità, picker genere/etichetta, empty state. I risultati (`DiscoveryLeadGrid`) sono esclusi su richiesta.

Metodo: Assessment A (design review su sorgente + ispezione browser dev :3000, desktop e mobile 375px). Assessment B: detector deterministico `detect.mjs` → **0 findings**; nessun overlay iniettato (detector pulito, ispezione manuale completa). UI attualmente in EN (bilingue): la nota storica "DIG in inglese in UI italiana" è superata.

## Design Health Score (solo pannello di controllo)

| # | Euristica | Score | Issue chiave |
|---|-----------|-------|--------------|
| 1 | Visibilità stato sistema | 3 | Spinner in DIG + Loading ok; stati attivi dei toggle chiari |
| 2 | Match sistema/mondo reale | 2 | "Affinity relative to" è astratto; il concetto di "profondità/audacia" dei preset non è mai nominato |
| 3 | Controllo e libertà | 3 | switchSeed pulisce lo stato; preset liberi; guarding params identici anti-duplicato |
| 4 | Consistenza e standard | 3 | Due segmented control identici con semantica diversa (mode vs intensità); icona DIG = icona Genere |
| 5 | Prevenzione errori | 3 | digReady disabilita DIG se vuoto; guard su params identici evita history duplicata |
| 6 | Riconoscimento vs ricordo | 3 | Chips + datalist ottimi; significato preset nascosto nei title nativi |
| 7 | Flessibilità ed efficienza | 2 | Nessun Enter-to-dig (l'Input non è in un form); nessuna scorciatoia; DIG raggiungibile solo col mouse in alto a dx |
| 8 | Estetica e minimalismo | 3 | Pulito e on-brand; ma affinità sovradimensionata e rottura layout mobile |
| 9 | Recupero da errori | 3 | Alert in testa; poco rilevante per il pannello (errori lato risultati) |
| 10 | Aiuto e documentazione | 2 | Nessuna guida; descrizioni preset presenti in i18n ma mai mostrate |
| **Totale** | | **27/40** | **Acceptable** |

## Verdetto anti-pattern
Non sembra AI-generated: monocromo disciplinato, hairline, square geometry, chips coerenti col design system. Detector deterministico pulito (0 findings su page.tsx). Il problema del pannello non è estetico ma di **gerarchia e struttura del flusso**: l'azione primaria è staccata dai suoi input, e su mobile si rompe.

## Carico cognitivo
Interleaving soggetto/modificatori: seed (alto) → profondità (alto) → affinità (metà) → genere+chips (basso). "Cosa scavare" è spezzato tra alto e basso con "come scavare" in mezzo. Ritmo piatto (mt-3 uniforme), nessun raggruppamento visivo. Moderato.

## Punti di forza
1. Preset Familiare/Bilanciato/Avventuroso al posto di uno slider grezzo: progressive disclosure corretta di `adventurousness`.
2. Picker genere a doppio canale: `Input` con `datalist` per ricerca libera + chips per i top-10 di libreria — recognition over recall ben fatto.
3. Empty state on-brand che insegna il prossimo passo ("Pronto per scavare / Premi Scava").

## Issue prioritarie

- **[P1] L'azione primaria è divorziata dai suoi input — e su mobile si rompe.** DIG vive in alto a destra; il soggetto che scegli (input genere + chips) è in basso a sinistra. Il flusso di lettura/interazione è top→bottom (seed → affinità → genere → chips) ma il bottone di commit è all'inizio, angolo opposto. Dopo aver scelto una chip in fondo, torni all'angolo in alto a destra per agire; e l'`Input` non è in un `<form>`, quindi **Enter non fa nulla**. Su mobile `justify-between` + `flex-wrap` isola DIG come blocco bianco a sé, renderizzato **prima** del picker genere: puoi "scavare" prima di aver scelto cosa. Fix: spostare DIG in fondo al pannello (dopo la scelta del soggetto), full-width su mobile; abilitare Enter-to-dig. Comando: /impeccable layout.

- **[P2] I preset profondità sono un gemello non etichettato del seed toggle.** Familiare/Bilanciato/Avventuroso è un segmented control visivamente identico a Genere/Etichetta, sulla stessa riga, ma uno sceglie il SOGGETTO (modalità) e l'altro l'INTENSITÀ. Due controlli identici, significato diverso, adiacenti = confondibili. Ed è l'unico cluster senza label uppercase: "START FROM" e "AFFINITY RELATIVE TO" sono etichettati, la profondità è nuda. Fix: dare una label ("PROFONDITÀ" / "AUDACIA") e differenziarlo visivamente dal mode toggle. Comando: /impeccable layout + clarify.

- **[P2] "Affinità rispetto a" sovradimensiona un controllo secondario e parla gergo.** È un select full-width — pesante quanto l'input genere, il soggetto vero — per un raffinamento avanzato che la maggior parte lascia su "Tutta la libreria". La label va a capo su due righe ed è astratta. Fix: demotarlo (inline, più piccolo, o dietro un'affordance "avanzate") e riformulare in qualcosa di concreto ("Misura il gusto rispetto a…"). Comando: /impeccable clarify + layout.

- **[P2] Significato dei preset nascosto nei tooltip nativi.** Un primo utente non può capire cosa sia la "profondità" né come differiscano i tre senza hover (mai su touch). La descrizione del preset attivo è già in i18n (`presetBalancedDesc` ecc.) ma non viene mai mostrata. Fix: renderizzare inline la descrizione del preset attivo sotto la riga. Comando: /impeccable clarify.

## Osservazioni minori
- Icona DIG (`Disc3`) = icona del seed "Genere": lieve collisione semantica.
- Il genere si auto-seleziona sul primo di libreria al load ("Abstract"/"Alternative"): un default arbitrario presentato identico a una scelta deliberata.
- Ritmo verticale piatto: `mt-3` uniforme, nessun raggruppamento "cosa" vs "come".

## Red flag personas
**Jordan (primo utente):** "Affinità rispetto a"? "Profondità"? Nessuna spiegazione inline; deve indovinare cosa fanno i tre preset. Il default genere pre-riempito lo può portare a scavare un genere che non ha scelto.
**Alex (power user):** nessun Enter-to-dig, nessuna scorciatoia; il bottone DIG è raggiungibile solo col mouse in alto a destra, lontano da dove finisce di scegliere. Attrito su ogni iterazione.
**Casey (mobile):** il layout si rompe — DIG orfano che precede i suoi input; l'azione primaria non è nel thumb-zone in fondo ma fluttua a metà form.

## Domande da considerare
- Se il gesto è "scavare", perché l'azione "Scava" è la prima cosa in alto e non la conclusione naturale in fondo alla scelta?
- I preset profondità e l'affinità meritano lo stesso peso visivo del soggetto (genere/etichetta)? O sono modificatori che dovrebbero stare sotto?
- Il pannello dovrebbe leggersi come una frase — "scava [genere] a profondità [X] rispetto a [Y]" — invece che come quattro controlli impilati senza gerarchia?
