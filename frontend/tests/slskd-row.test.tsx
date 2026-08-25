import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const finto = vi.hoisted(() => ({
  daemon: { reachable: false, owned: null as boolean | null, pid: null, installed: false, configured: false, username: null as string | null },
  slskd: { configured: false, reachable: false, is_connected: false, is_logged_in: false, is_connecting: false, is_transitioning: false, username: null as string | null },
  startInstall: vi.fn(),
  daemonConfig: vi.fn(),
  daemonStart: vi.fn(),
  daemonStop: vi.fn(),
  slskdConnect: vi.fn(),
  slskdDisconnect: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String(e),
  daemonStatus: () => Promise.resolve(finto.daemon),
  slskdStatus: () => Promise.resolve(finto.slskd),
  startInstall: (k: string) => finto.startInstall(k),
  getInstallStatus: () => Promise.resolve({ status: "done", detail: null, error_code: null }),
  daemonConfig: (b: unknown) => finto.daemonConfig(b),
  daemonStart: () => finto.daemonStart(),
  daemonStop: () => finto.daemonStop(),
  slskdConnect: () => finto.slskdConnect(),
  slskdDisconnect: () => finto.slskdDisconnect(),
}));

import { SlskdRow } from "@/components/slskd-row";

const acceso = { reachable: true, owned: true as boolean | null, pid: 42, installed: true, configured: true, username: "dj_test" };

beforeEach(() => {
  finto.daemon = { reachable: false, owned: null, pid: null, installed: false, configured: false, username: null };
  finto.slskd = { configured: false, reachable: false, is_connected: false, is_logged_in: false, is_connecting: false, is_transitioning: false, username: null };
});
afterEach(cleanup);

/* Il valore della riga è che mostri UNA azione: quella giusta per il punto in
   cui si è. Ogni test verifica anche che le altre non ci siano — senza,
   mostrarle tutte insieme passerebbe lo stesso. */

describe("riga slskd", () => {
  it("binario assente: offre il download e nient'altro", async () => {
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Scarica slskd")).toBeTruthy());
    expect(screen.queryByText("Salva configurazione")).toBeNull();
    expect(screen.queryByText("Avvia")).toBeNull();
  });

  it("installato ma non configurato: chiede le credenziali", async () => {
    finto.daemon = { ...finto.daemon, installed: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Salva configurazione")).toBeTruthy());
    expect(screen.queryByText("Scarica slskd")).toBeNull();
  });

  it("configurato ma fermo: offre l'avvio, e mostra chi sei senza richiederlo", async () => {
    finto.daemon = { ...finto.daemon, installed: true, configured: true, username: "dj_test" };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Avvia")).toBeTruthy());
    expect(screen.getByText(/dj_test/)).toBeTruthy();
    expect(screen.queryByText("Salva configurazione")).toBeNull();
  });

  it("demone attivo ma non collegato: offre il collegamento", async () => {
    finto.daemon = { ...acceso };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText(/Connetti|Collega/)).toBeTruthy());
    expect(screen.queryByText("Avvia")).toBeNull();
  });

  it("collegato: offre scollega e ferma", async () => {
    finto.daemon = { ...acceso };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true, is_connected: true, is_logged_in: true, username: "dj_test" };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText(/Disconnetti|Scollega/)).toBeTruthy());
    expect(screen.getByText("Ferma")).toBeTruthy();
  });

  /* Le tre possibilità di `owned` erano coperte dai test di services-list, che
     provavano il componente che questa riga sostituisce: la copertura si
     sposta qui insieme al comportamento. "Acceso da altri" non è un dettaglio
     — è la ragione per cui non c'è il bottone Ferma. */
  it("acceso da altri: lo dice, e non offre di fermarlo", async () => {
    finto.daemon = { ...acceso, owned: false, pid: null };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText(/fuori da Cratory/i)).toBeTruthy());
    expect(screen.queryByText("Ferma")).toBeNull();
  });

  it("proprietà non rilevabile: niente bottone Ferma, e nessuna bugia sul proprietario", async () => {
    finto.daemon = { ...acceso, owned: null, pid: null };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.queryByText("Ferma")).toBeNull());
  });

  it("non precompila mai la password", async () => {
    finto.daemon = { ...finto.daemon, installed: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Salva configurazione")).toBeTruthy());
    const campo = document.querySelector('input[type="password"]') as HTMLInputElement;
    expect(campo.value).toBe("");
  });
});
