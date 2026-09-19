import { test, expect } from "@playwright/test";

// Percorso del set manuale (spec 2026-09-15, tappe 1-2) contro il backend reale
// avviato dalla configurazione Playwright con DB vuoto. Niente playlist né
// tracce, quindi il set nasce senza origine e il materiale arriva dalla ricerca
// in libreria: le tracce le creiamo via API prima di aprire la pagina.

/** Crea `n` tracce possedute e ritorna i loro id, nell'ordine. */
async function seminaTracce(request: import("@playwright/test").APIRequestContext, n: number,
                            prefisso = "") {
  // Senza `prefisso` due chiamate creano le STESSE tracce: import-manual
  // deduplica per artista+titolo. Va bene quasi sempre; serve distinguerle solo
  // quando il test vuole due playlist con contenuti diversi.
  const righe = Array.from({ length: n }, (_, i) =>
    `Artista ${prefisso}${i} - Traccia ${prefisso}${i}`).join("\n");
  const res = await request.post("/api/playlists/import-manual", {
    // Nome unico anche fra worker paralleli: due \`Date.now()\` nello stesso
    // millisecondo darebbero due playlist omonime, e i test che contano i set
    // per nome si conterebbero addosso.
    data: { name: `E2E ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, text: righe },
  });
  expect(res.ok()).toBeTruthy();
  // L'import manuale risponde con un report (`playlist_id`), non con la playlist.
  const report = await res.json();
  const tracce = await (await request.get(`/api/playlists/${report.playlist_id}/tracks`)).json();
  return { playlistId: report.playlist_id as number, trackIds: tracce.map((t: { id: number }) => t.id) };
}

test("alternative e riserva sopravvivono al ricaricamento", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 4);

  // Set dalla playlist appena creata, con due tracce già nel percorso: la pagina
  // parte da uno stato utile invece che vuoto.
  const creato = await request.post("/api/sets/manual", { data: { playlist_ids: [playlistId] } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: [trackIds[0], trackIds[1]] },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  // Nel percorso: la stessa traccia compare anche fra il materiale, che elenca
  // pure quelle già nel set.
  await expect(page.getByTestId("path-panel").getByText("Traccia 0")).toBeVisible();

  // Seleziona la prima riga del percorso, poi tieni la terza traccia come sua
  // candidata: il comando compare sulle righe del materiale solo con una riga
  // selezionata, perché senza non avrebbe un punto a cui attaccarla.
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 0/ }).click();
  const rigaMateriale = page.getByTestId("material-panel").locator("li")
    .filter({ hasText: "Traccia 2" });
  await rigaMateriale.getByTitle("Tieni come alternativa").click();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 2")).toBeVisible();

  // Sceglila: diventa attiva e la precedente resta fra le candidate.
  await page.getByTestId("detail-panel").getByRole("button", { name: "Usa" }).click();
  await expect(page.getByTestId("path-panel").getByText("Traccia 2")).toBeVisible();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 0")).toBeVisible();

  // Metti da parte la quarta traccia.
  await page.getByTestId("material-panel").locator("li").filter({ hasText: "Traccia 3" })
    .getByTitle("Metti da parte per la serata").click();
  await expect(page.getByTestId("reserve-panel").getByText("Traccia 3")).toBeVisible();

  // Ricarica: percorso, candidate e riserva sono ancora lì.
  await page.reload();
  await expect(page.getByTestId("path-panel").getByText("Traccia 2")).toBeVisible();
  await expect(page.getByTestId("reserve-panel").getByText("Traccia 3")).toBeVisible();
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 2/ }).click();
  await expect(page.getByTestId("detail-panel").getByText("Traccia 0")).toBeVisible();
});

test("sequenze, banco e annulla sopravvivono al ricaricamento", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 4);
  const creato = await request.post("/api/sets/manual", { data: { playlist_ids: [playlistId] } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: trackIds },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  const percorso = page.getByTestId("path-panel");
  await expect(percorso.getByText("Traccia 0")).toBeVisible();

  // Raggruppa le due centrali: il percorso resta di quattro righe, cambia solo
  // come e' diviso.
  const riga = (n: number) => percorso.locator("li").filter({ hasText: `Traccia ${n}` });
  await riga(1).getByLabel("Seleziona la riga").check();
  await riga(2).getByLabel("Seleziona la riga").check();
  await page.getByRole("button", { name: "Raggruppa" }).click();
  await expect(percorso.locator("li")).toHaveCount(4);
  await expect(percorso.locator("section")).toHaveCount(3);

  // Parcheggia la sequenza centrale sul banco: due righe restano nel percorso.
  await percorso.locator("section").nth(1).getByTitle("Sposta sul banco").click();
  await expect(page.getByTestId("bench-panel").getByText("Traccia 1")).toBeVisible();
  await expect(percorso.locator("li")).toHaveCount(2);

  // Due annulla riportano il percorso a quattro righe in una sequenza sola.
  await page.getByRole("button", { name: "Annulla" }).click();
  await expect(percorso.locator("li")).toHaveCount(4);
  await page.getByRole("button", { name: "Annulla" }).click();
  await expect(percorso.locator("section")).toHaveCount(1);

  // Lo stato annullato e' quello salvato, non una finzione della pagina.
  await page.reload();
  await expect(page.getByTestId("path-panel").locator("li")).toHaveCount(4);
  await expect(page.getByTestId("path-panel").locator("section")).toHaveCount(1);
});

test("l'appunto di un passaggio non si trasferisce e non si perde", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 3);
  const creato = await request.post("/api/sets/manual", { data: { playlist_ids: [playlistId] } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: [trackIds[0], trackIds[1]] },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  const percorso = page.getByTestId("path-panel");
  await expect(percorso.getByText("Traccia 0")).toBeVisible();

  // Sulla seconda riga, l'appunto del passaggio che ci arriva.
  await percorso.getByRole("button", { name: /Traccia 1/ }).click();
  const appunto = page.getByTestId("transition-panel-in")
    .getByPlaceholder("Come ci entro, cosa taglio…");
  await appunto.fill("entra sul break");
  // Il blur fa PARTIRE il salvataggio, non lo compie: la PUT e' asincrona.
  // Gli altri ricaricamenti di questo file sono preceduti da un'attesa
  // sull'interfaccia (una pastiglia che compare, una sezione che sparisce) che
  // di fatto aspetta la risposta; qui no, perche' la casella mostra gia' il
  // testo digitato e non c'e' niente di nuovo da aspettare a schermo. Senza
  // questa attesa la GET del ricaricamento puo' arrivare al server PRIMA che
  // la PUT abbia scritto, e la pagina riparte dal documento di prima, con
  // l'appunto vuoto e la revisione vecchia — da li' in poi la prima mutazione
  // prende 409 e la riga non se ne va. Coi worker in parallelo il backend
  // rallenta e la corsa la vinceva il ricaricamento.
  const salvato = page.waitForResponse((r) =>
    r.request().method() === "PUT" && r.url().includes("/pair-notes") && r.ok());
  await appunto.blur();
  await salvato;

  // Salvato davvero: sopravvive al ricaricamento.
  await page.reload();
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 1/ }).click();
  await expect(page.getByTestId("transition-panel-in")
    .getByPlaceholder("Come ci entro, cosa taglio…")).toHaveValue("entra sul break");

  // Tolgo la prima traccia: quel passaggio non esiste piu'.
  const prima = page.getByTestId("path-panel").locator("li").filter({ hasText: "Traccia 0" });
  await prima.getByTitle("Togli dal percorso").click();
  await expect(page.getByTestId("path-panel").locator("li")).toHaveCount(1);
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 1/ }).click();
  await expect(page.getByTestId("transition-panel-in")).toHaveCount(0);

  // La rimetto: «Aggiungi al percorso» la mette in coda, quindi la coppia
  // sarebbe 1->0, che di suo non ha appunto. La riporto davanti e la coppia
  // 0->1 ritrova il suo: era legato alle tracce, non alle righe.
  await page.getByTestId("material-panel").locator("li").filter({ hasText: "Traccia 0" })
    .getByTitle("Aggiungi al percorso").click();
  await expect(page.getByTestId("path-panel").locator("li")).toHaveCount(2);
  await page.getByTestId("path-panel").locator("li").filter({ hasText: "Traccia 0" })
    .getByTitle("Su").click();
  await expect(page.getByTestId("path-panel").locator("li").first()).toContainText("Traccia 0");
  await page.getByTestId("path-panel").getByRole("button", { name: /Traccia 0/ }).click();
  await expect(page.getByTestId("transition-panel-out")
    .getByPlaceholder("Come ci entro, cosa taglio…")).toHaveValue("entra sul break");
});

test("il varco si fa riempire dal generatore, e la scheda di preparazione lo racconta", async ({ page, request }) => {
  const { playlistId, trackIds } = await seminaTracce(request, 6);
  const creato = await request.post("/api/sets/manual", { data: { playlist_ids: [playlistId] } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, {
    data: { expected_revision: 0, track_ids: [trackIds[0], trackIds[1]] },
  });

  await page.goto(`/sets/manual?id=${set.id}`);
  const percorso = page.getByTestId("path-panel");
  await expect(percorso.getByText("Traccia 0")).toBeVisible();

  // Lascia un varco fra le due tracce.
  await percorso.locator("li").filter({ hasText: "Traccia 0" })
    .getByTitle("Lascia un varco dopo questa riga").click();
  await expect(percorso.locator("li")).toHaveCount(3);

  // Falla riempire con due tracce: il percorso ne ha quattro, nessun varco.
  await percorso.getByTitle("Riempi il varco").click();
  const pannello = page.getByTestId("fill-gap");
  await pannello.getByLabel("Quante tracce").fill("2");
  await pannello.getByText("Riempi").click();
  await expect(percorso.locator("li")).toHaveCount(4);
  await expect(percorso.getByText("Varco")).toHaveCount(0);

  // Un annulla solo riapre il varco: il riempimento è una revisione sola.
  await page.getByRole("button", { name: "Annulla" }).click();
  await expect(percorso.locator("li")).toHaveCount(3);
  await expect(percorso.getByText("Varco")).toHaveCount(1);

  // La scheda di preparazione: l'anteprima è la risposta del server.
  await page.getByRole("button", { name: "Esporta" }).click();
  await page.getByText("Scheda di preparazione").click();
  const anteprima = page.getByTestId("export-preview");
  await expect(anteprima).toContainText("Traccia 0");
  await expect(anteprima).toContainText("varco");
});

test("una bozza abbandonata non lascia un set vuoto in archivio", async ({ page, request }) => {
  const { playlistId } = await seminaTracce(request, 2, "boz");
  // Il nome della playlist e' unico per test (E2E <timestamp>) e un set creato
  // da lei lo eredita: contare TUTTI i set sarebbe inaffidabile, perche' i
  // worker di Playwright girano in parallelo e ne creano altri.
  const nome = (await (await request.get(`/api/playlists/${playlistId}`)).json()).name as string;
  const quantiMiei = async () => {
    const tutti = (await (await request.get("/api/sets")).json()) as { name: string }[];
    return tutti.filter((x) => x.name === nome).length;
  };
  expect(await quantiMiei()).toBe(0);

  // Apri il banco su una bozza e scegli una playlist: non deve salvare niente.
  await page.goto(`/sets/manual?playlist=${playlistId}`);
  await expect(page.getByTestId("material-panel").getByText("Traccia boz0")).toBeVisible();
  await page.goto("/sets");
  await expect(page.getByText("Prepara un set")).toBeVisible();
  expect(await quantiMiei()).toBe(0);

  // Rifallo, ma stavolta metti dentro una traccia: ora il set esiste.
  await page.goto(`/sets/manual?playlist=${playlistId}`);
  await page.getByTestId("material-panel").locator("li").filter({ hasText: "Traccia boz0" })
    .getByTitle("Aggiungi al percorso").click();
  await expect(page.getByTestId("path-panel").getByText("Traccia boz0")).toBeVisible();
  await expect(page).toHaveURL(/\/sets\/manual\?id=\d+/);
  expect(await quantiMiei()).toBe(1);
});

test("un set pesca da due playlist insieme", async ({ page, request }) => {
  const a = await seminaTracce(request, 2, "A");
  const b = await seminaTracce(request, 2, "B");
  const creato = await request.post("/api/sets/manual", {
    data: { playlist_ids: [a.playlistId] },
  });
  const set = await creato.json();

  await page.goto(`/sets/manual?id=${set.id}`);
  const origini = page.getByTestId("sources-panel");
  await expect(origini.getByLabel("Aggiungi una playlist")).toBeVisible();

  // Il materiale ha solo le tracce della prima playlist.
  const materiale = page.getByTestId("material-panel");
  const primaTraccia = await materiale.locator("li").count();

  // Aggiungi la seconda: il materiale cresce.
  await origini.getByLabel("Aggiungi una playlist").selectOption(String(b.playlistId));
  await expect(materiale.locator("li")).not.toHaveCount(primaTraccia);
  await expect(materiale.getByText("Traccia B0")).toBeVisible();
});
