# 01 — Product Vision

## Contesto

Webapp personale per aiutare un DJ amatoriale a preparare set in modo più intelligente e a migliorare rapidamente. Importa dati da un export XML di Rekordbox, arricchisce le tracce tramite Spotify (e opzionalmente Discogs/MusicBrainz), e usa un agente AI per costruire set coerenti, spiegare le scelte musicali e suggerire come ampliare la libreria in modo contestualizzato.

**Il progetto non è un software per suonare musica.** È un assistente di preparazione, analisi e crate digging.

## Obiettivo principale

La webapp deve:

1. importare la libreria da Rekordbox XML
2. riconoscere tracce Spotify, SoundCloud e file locali
3. arricchire i metadata tramite Spotify
4. permettere di filtrare e interrogare la libreria
5. generare set DJ coerenti su base artista, genere, BPM, tonalità, durata e intenzione musicale
6. usare un agente AI per interpretare richieste in linguaggio naturale
7. spiegare perché una scaletta funziona
8. suggerire alternative per ogni traccia del set
9. suggerire come ampliare la libreria (artista, etichetta, genere, lacune della collection)
10. esportare il set generato (playlist Spotify, CSV, testo)

## Cosa NON deve fare (prima versione)

- suonare file audio
- sostituire Rekordbox
- scaricare audio da Spotify
- fare scraping non autorizzato
- fare tracking dettagliato dei progressi dell'utente
- richiedere tagging manuale dei brani
- basarsi su mood inseriti manualmente
- implementare machine learning complesso
- essere multiutente
- avere app mobile nativa

Il focus è: **creazione set, spiegazione, suggerimenti intelligenti, crate digging contestualizzato**.

## Vincoli importanti

- Non implementare download audio da Spotify.
- Non usare dati Spotify per BPM o key — Rekordbox è la fonte primaria per i dati DJ (BPM, tonalità, durata, beatgrid, cue point, play count).
- Spotify serve per arricchire i metadata: titolo, artista, album, cover, link, info artista.
- Non obbligare l'utente a taggare manualmente.
- Non inventare metadata musicali.
- Tenere separato il motore tecnico deterministico dall'agente AI (vedi [02-architecture.md](02-architecture.md)).
- Ogni set generato deve avere spiegazioni.
- Ogni suggerimento di espansione libreria deve essere contestualizzato.
- Ogni output AI deve essere validato prima di essere mostrato come definitivo.

## Regole per AI e fonti esterne

L'AI deve:

- evitare di inventare dati fattuali
- citare internamente la fonte del dato quando disponibile
- distinguere tra dato verificato, inferenza musicale e ipotesi creativa
- non presentare ipotesi come certezze
- produrre query di ricerca pratiche anche quando non è sicura del suggerimento
- dare priorità a suggerimenti utili per set reali, non solo culturalmente interessanti

## Criterio di successo

La webapp è riuscita se ogni volta che la apro posso:

1. importare o aggiornare la mia libreria Rekordbox
2. capire rapidamente quali tracce ho a disposizione
3. chiedere un set in linguaggio naturale
4. ricevere una scaletta tecnicamente plausibile e musicalmente spiegata
5. modificare la scaletta con alternative sensate
6. capire cosa cercare per ampliare la libreria in modo mirato
7. esportare il set o salvarlo per usarlo in Rekordbox/Spotify
