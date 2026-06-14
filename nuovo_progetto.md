\# Progetto di modifica: nuova logica Playlist to Set Builder



\## Obiettivo



Modificare l’app esistente eliminando la dipendenza da Rekordbox come fonte principale di analisi e trasformandola in un sistema che genera bozze di DJ set a partire da playlist create dall’utente su servizi streaming come Spotify e SoundCloud.



La nuova logica prevede che l’utente importi una playlist, l’app recuperi i metadati disponibili tramite API, arricchisca le tracce con dati musicali esterni e generi una proposta di set ordinata, spiegabile e modificabile manualmente.



\## Cambio di paradigma



\### Logica precedente



L’app era pensata per lavorare su una libreria già analizzata o parzialmente analizzata tramite Rekordbox.



I dati principali erano:



\* BPM da Rekordbox

\* Tonalità da Rekordbox

\* Tracce già caricate o suonate

\* Libreria locale o XML Rekordbox



\### Nuova logica



Rekordbox viene rimosso dal flusso principale.



La playlist streaming diventa il punto di partenza operativo.



Nuovo flusso:



```text

Playlist Spotify / SoundCloud

↓

Import tracce e metadati

↓

Normalizzazione e deduplica

↓

Arricchimento BPM, tonalità, genere, mood, energia

↓

Generazione bozza set

↓

Editor manuale

↓

Export scaletta / nuova playlist / report

```



\## Modifiche funzionali richieste



\### 1. Import playlist



Aggiungere o modificare il modulo di importazione per supportare:



\* playlist Spotify dell’utente autenticato

\* playlist collaborative accessibili all’utente

\* playlist SoundCloud

\* liked tracks, se disponibili via API



Per ogni traccia importata salvare almeno:



```text

title

artist

duration

platform

platform\_track\_id

playlist\_id

playlist\_name

url

artwork\_url

isrc, se disponibile

added\_at

```



\## 2. Rimozione dipendenza Rekordbox



Eliminare dal core dell’app la necessità di avere dati Rekordbox.



I dati Rekordbox, se presenti in vecchie installazioni, potranno restare come fonte storica opzionale, ma non devono più essere obbligatori per generare un set.



Stati traccia consigliati:



```text

imported

enriched

ready\_for\_set

missing\_features

low\_confidence

```



\## 3. Arricchimento metadati



Aggiungere un livello di enrichment esterno per ottenere:



```text

bpm

key

camelot\_key

genre\_primary

genre\_secondary

mood

energy

danceability

vocalness

label

release\_date

confidence

source

```



Provider possibili:



```text

MusicBrainz per identificazione, ISRC, release, label

GetSongBPM o Tunebat per BPM e tonalità

Cyanite o Soundcharts per analisi più avanzata, mood, energia e similarità

Last.fm o tag esterni per genere

```



Il matching non deve basarsi solo su titolo e artista.



Priorità matching:



```text

1\. ISRC

2\. platform\_track\_id

3\. artist + title + duration

4\. fuzzy match artist + title

```



\## 4. Nuovo motore di generazione set



Creare un modulo Set Builder che prenda in input:



```text

playlist\_id

durata target

range BPM desiderato

mood iniziale

mood finale

progressione energia

preferenze genere

preferenze artisti

vincoli opzionali dell’utente

```



E produca:



```text

sequenza tracce

ruolo di ogni traccia

motivazione della posizione

nota di transizione

confidence della scelta

alternative suggerite

```



Esempio ruoli:



```text

intro

warmup

groove

transition

peak

release

closing

```



\## 5. Separazione tra algoritmo e AI



Non affidare tutta la generazione all’LLM.



Implementare prima un motore deterministico che calcoli punteggi:



```text

bpm\_compatibility\_score

key\_compatibility\_score

energy\_progression\_score

genre\_similarity\_score

mood\_coherence\_score

transition\_score

```



L’AI deve intervenire dopo per:



```text

interpretare il prompt utente

scegliere una direzione narrativa

spiegare le transizioni

proporre alternative

evidenziare buchi nella playlist

suggerire artisti, label o generi da esplorare

```



\## 6. Analisi dei buchi nella playlist



Aggiungere una funzione che analizzi la playlist e segnali problemi utili per il DJ set:



```text

mancano tracce di apertura

mancano tracce ponte tra due range BPM

mancano tracce compatibili armonicamente

playlist troppo uniforme come energia

playlist troppo dispersiva per genere

troppe tracce vocal consecutive

pochi brani adatti al peak

```



Output esempio:



```text

La playlist ha molte tracce tra 122 e 124 BPM, ma poche tracce tra 126 e 128 BPM.

Potrebbe servire una sezione ponte per rendere più naturale la crescita del set.

```



\## 7. Editor set



Aggiungere o modificare l’interfaccia per permettere all’utente di:



```text

vedere la scaletta generata

spostare tracce manualmente

bloccare una traccia in posizione

escludere una traccia

chiedere alternative per una posizione

rigenerare una sezione del set

vedere spiegazioni sulle transizioni

```



\## 8. Export



Prevedere export in:



```text

Markdown

CSV

nuova playlist Spotify, se permesso dalle API

lista link SoundCloud

```



\## Criterio di successo



La modifica sarà considerata riuscita se l’utente potrà:



```text

1\. scegliere una playlist streaming

2\. ottenere una bozza di set coerente

3\. capire perché le tracce sono state ordinate in quel modo

4\. correggere manualmente la scaletta

5\. esportare il risultato finale

```



L’app non deve promettere di sostituire completamente l’ascolto umano, ma deve ridurre drasticamente il tempo necessario per trasformare una playlist grezza in una bozza di set utilizzabile.



