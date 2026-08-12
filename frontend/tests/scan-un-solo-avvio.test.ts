import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * F4 Task 4 — un solo bottone. La correzione al brief (task-4-brief.md) ha
 * superato la versione originale di questo test: `index-nav.tsx` resta su
 * `startLibraryIndex` (lib/api), il bottone di Organize resta su `startScan`
 * (lib/organize/api) — nomi diversi per due strati diversi, forzarne uno
 * creerebbe un import Cratory -> Organize che F5 dovrebbe poi sbrogliare.
 *
 * L'invariante da provare non è lessicale ma comportamentale: i due avvii
 * devono finire sullo STESSO job lato backend. Lato frontend è verificabile
 * solo fino all'endpoint (le due funzioni chiamano URL diversi per
 * costruzione: /api/library/index vs /api/organize/scan); l'unificazione vera
 * e propria è che entrambe le rotte, lato backend, delegano alla stessa
 * `scan_job.start_job()` dello stesso modulo `app.organize.services.scan_job`
 * (singleton in memoria, F4 Task 3) — è questo che rende "un solo job" più di
 * un'affermazione a parole.
 */

const nav = readFileSync(resolve(__dirname, "../components/index-nav.tsx"), "utf8");
const libApiTracks = readFileSync(resolve(__dirname, "../lib/api/tracks.ts"), "utf8");
const organizeApi = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");
const organizeFilesPage = readFileSync(resolve(__dirname, "../app/organize/files/page.tsx"), "utf8");

const tracksRouter = readFileSync(
  resolve(__dirname, "../../backend/app/routers/tracks.py"), "utf8",
);
const scanRouter = readFileSync(
  resolve(__dirname, "../../backend/app/organize/routers/scan.py"), "utf8",
);

describe("un solo avvio della scansione (F4 Task 4)", () => {
  it("la nav di Cratory avvia l'indicizzazione tramite l'entrypoint condiviso di lib/api", () => {
    expect(nav).toContain("startLibraryIndex");
  });

  it("startLibraryIndex (lib/api) chiama l'alias del job unico, non un endpoint separato", () => {
    expect(libApiTracks).toMatch(/apiPost<LibraryIndexJob>\(\s*["']\/api\/library\/index["']\s*\)/);
  });

  it("il bottone di scan in Organize/Files avvia il job tramite startScan (lib/organize/api)", () => {
    // Non basta che il nome compaia nel file (potrebbe restare solo nella
    // destructuring di useJobs() dopo che onScan è stato riscritto): serve
    // che sia effettivamente invocato.
    expect(organizeFilesPage).toMatch(/\bawait\s+startScan\(/);
    expect(organizeApi).toMatch(/apiSend<ScanJobState>\(\s*["']POST["'],\s*["']\/scan["']/);
  });

  it("sul backend, entrambe le rotte (/api/library/index e /api/organize/scan) chiamano scan_job.start_job dello stesso modulo: un solo job, non due", () => {
    // Stesso import in entrambi i router: senza questo le due rotte potrebbero
    // chiamare due `scan_job` diversi (due moduli con lo stesso nome) e
    // finire su due stati/lock in memoria distinti.
    expect(tracksRouter).toContain("from app.organize.services import apply_job, scan_job");
    expect(scanRouter).toContain("from app.organize.services import apply_job, scan_job");

    // La rotta di Cratory è dichiarata alias esplicito del job unico: la sua
    // definizione (dal decorator in poi) deve invocare scan_job.start_job().
    const aliasStart = tracksRouter.indexOf('@router.post("/library/index"');
    expect(aliasStart).toBeGreaterThan(-1);
    const nextRouteStart = tracksRouter.indexOf("\n@router.", aliasStart + 1);
    const aliasBody = tracksRouter.slice(aliasStart, nextRouteStart === -1 ? undefined : nextRouteStart);
    expect(aliasBody).toContain("scan_job.start_job()");

    // La rotta canonica di Organize chiama la stessa funzione.
    expect(scanRouter).toContain("scan_job.start_job(");
  });
});
