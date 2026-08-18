import { describe, expect, it, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ServiceGuide } from "@/components/setup/service-guide";

describe("ServiceGuide", () => {
  afterEach(cleanup);

  it("docsUrl assente: niente link 'Apri il provider' (fix 5c)", () => {
    // Un href="" naviga alla pagina corrente: click → reload di /setup e
    // l'utente perde il passo in cui si trova. Meglio nessun link.
    render(<ServiceGuide service="slskd" docsUrl="" copyValue={null} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByText(/apri il provider|open the provider/i)).toBeNull();
  });

  it("docsUrl presente: il link c'è e punta lì", () => {
    render(<ServiceGuide service="slskd" docsUrl="https://github.com/slskd/slskd" copyValue={null} />);
    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.href).toBe("https://github.com/slskd/slskd");
  });
});
