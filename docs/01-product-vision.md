# 01 — Product Vision

## Contesto

Webapp personale per aiutare un DJ a trasformare rapidamente una **playlist Spotify** in una **bozza di DJ set** coerente, spiegata e modificabile a mano — e per scoprire nuova musica compatibile con il proprio stile. Importa la playlist, recupera i metadati via API, arricchisce le tracce con dati musicali esterni (BPM, tonalità, genere, mood, energia) e genera una proposta di set ordinata.

**Il progetto non è un software per suonare musica.** È un assistente di preparazione, analisi e scoperta.

## Obiettivo principale

La webapp deve:

1. importare una playlist Spotify dell'utente (incluse collaborative e liked)
2. normalizzare e deduplicare le tracce importate
3. arricchire i metadata via API e con provider musicali esterni (BPM, key, mood, energia, genere, label)
4. permettere di filtrare e interrogare la libreria di tracce raccolte dalle playlist
5. generare bozze di DJ set coerenti su base BPM, tonalità, energia, mood, genere, durata e intenzione musicale
6. assegnare a ogni traccia un **ruolo** nell'arco del set (intro, warmup, groove, transition, peak, release, closing)
7. usare un agente AI per interpretare richieste in linguaggio naturale e dare una direzione narrativa con conoscenza completa della playlist
8. spiegare perché una scaletta funziona e annotare le transizioni
9. segnalare i **buchi della playlist** rispetto a un set (aperture, ponti BPM, peak, vocal consecutivi…)
10. **suggerire nuova musica** compatibile con il set/playlist (Discovery mode): colma i buchi specifici o espande il tuo stile, simulando il comportamento di un DJ pro nella ricerca di nuovi pezzi
11. permettere editing manuale (sposta, blocca, escludi, rigenera sezione, chiedi alternative)
12. esportare il risultato (Markdown, CSV, nuova playlist Spotify)

## Cosa NON deve fare

* suonare o scaricare audio
* richiedere tagging manuale dei brani
* basarsi su mood inseriti manualmente
* implementare machine learning complesso
* essere multiutente o avere app mobile nativa

Il focus è: **playlist → bozza di set spiegata e modificabile → scoperta di musica nuova compatibile, in poco tempo**.

## Vincoli importanti

* Non implementare download audio.
* BPM, tonalità e feature musicali arrivano dall'enrichment esterno (GetSongBPM, MusicBrainz, Last.fm): **mai inventati**.
* Spotify serve per identità traccia e metadata editoriali (titolo, artista, album, cover, durata, ISRC, url): non fornisce BPM/key affidabili per il mixing.
* Non obbligare l'utente a taggare manualmente.
* Tenere separato il motore tecnico deterministico dall'agente AI (vedi [02-architecture.md](02-architecture.md)).
* Ogni set generato deve avere spiegazioni; ogni output AI deve essere validato prima di essere mostrato come definitivo.
* I suggerimenti Discovery devono essere contestuali al set/playlist specifico, non generici: un DJ pro cerca musica che risolve un problema preciso (BPM mancante, gap armonico, sezione energetica debole).

## Regole per AI e fonti esterne

L'AI deve:

* evitare di inventare dati fattuali
* distinguere tra dato verificato (da fonte esterna), inferenza musicale e ipotesi creativa
* non presentare ipotesi come certezze
* produrre query di ricerca pratiche quando suggerisce artisti/label/generi da esplorare
* dare priorità a suggerimenti utili per set reali

## Criterio di successo

La modifica è riuscita se l'utente può:

1. scegliere una playlist streaming
2. ottenere una bozza di set coerente
3. capire perché le tracce sono state ordinate in quel modo
4. correggere manualmente la scaletta
5. esportare il risultato finale

L'app non promette di sostituire l'ascolto umano, ma deve **ridurre drasticamente il tempo** necessario per trasformare una playlist grezza in una bozza di set utilizzabile.

