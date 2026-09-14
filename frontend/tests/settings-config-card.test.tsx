import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigCard } from "@/components/settings/config-card";
import type { ConfigSettings, FieldState } from "@/lib/api";

const getConfigSettings = vi.fn();
const patchConfigSettings = vi.fn();
const pickerAvailability = vi.fn();
const pickPath = vi.fn();
const setDownloadSlots = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getConfigSettings: (...a: unknown[]) => getConfigSettings(...a),
  patchConfigSettings: (...a: unknown[]) => patchConfigSettings(...a),
  setLibraryShare: vi.fn(),
  setDownloadSlots: (...a: unknown[]) => setDownloadSlots(...a),
  pickerAvailability: (...a: unknown[]) => pickerAvailability(...a),
  pickPath: (...a: unknown[]) => pickPath(...a),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const field = (value: string): FieldState =>
  ({ value, source: "env", valid: true, detail: null });

const secret = (): ConfigSettings["secrets"][keyof ConfigSettings["secrets"]] => ({
  configured: false,
  source: "env",
  hint: null,
});

const CONFIG: ConfigSettings = {
  library_root: field("/Users/x/Music"),
  archive_root: field(""),
  slskd_download_dir: field("/Users/x/Downloads"),
  slskd_url: field("http://localhost:5030"),
  slskd_config_path: field(""),
  share_library: false,
  download_slots: 3,
  warning: null,
  ai_model: field("claude-sonnet-4-5"),
  secrets: {
    spotify_client_id: secret(),
    spotify_client_secret: secret(),
    ai_api_key: secret(),
    discogs_token: secret(),
    acoustid_api_key: secret(),
    slskd_api_key: secret(),
  },
  spotify_redirect_uri: "http://127.0.0.1:8000/api/spotify/callback",
};

async function mount(available: boolean, section: "library" | "downloads" = "library") {
  getConfigSettings.mockResolvedValue(CONFIG);
  pickerAvailability.mockResolvedValue({ available });
  const view = render(<ConfigCard section={section} />);
  await act(async () => {});
  return view;
}

describe("ConfigCard + picker", () => {
  it("in Libreria mostra Sfoglia solo sulle due cartelle", async () => {
    await mount(true);
    expect(screen.getAllByRole("button", { name: "Sfoglia…" })).toHaveLength(2);
  });

  it("senza picker nessun pulsante Sfoglia (resta l'input testuale)", async () => {
    await mount(false);
    expect(screen.queryByRole("button", { name: "Sfoglia…" })).toBeNull();
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("il percorso scelto riempie la bozza senza salvare", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: "/Volumes/Dischi/Musica" });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Volumes/Dischi/Musica")).toBeTruthy();
    expect(patchConfigSettings).not.toHaveBeenCalled();
  });

  it("annullo del dialog: la bozza non cambia", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: null });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("errore del picker mostrato nel banner della card", async () => {
    await mount(true);
    pickPath.mockRejectedValue(new Error("Un dialog di scelta è già aperto sulla macchina del backend."));
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByText(/già aperto/)).toBeTruthy();
  });
});

const spinValue = (el: HTMLElement) => (el as HTMLInputElement).value;

describe("ConfigCard + download slots", () => {
  it("valore svuotato: nessuna scrittura e il campo torna al valore in vigore", async () => {
    await mount(true, "downloads");
    const input = screen.getByRole("spinbutton");
    expect(spinValue(input)).toBe("3");

    fireEvent.change(input, { target: { value: "" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    expect(setDownloadSlots).not.toHaveBeenCalled();
    expect(spinValue(input)).toBe("3");
    expect(screen.getByText(/ripristinato/)).toBeTruthy();
  });

  it("valore fuori scala (>10): nessuna scrittura e il campo torna al valore in vigore", async () => {
    await mount(true, "downloads");
    const input = screen.getByRole("spinbutton");

    fireEvent.change(input, { target: { value: "15" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    expect(setDownloadSlots).not.toHaveBeenCalled();
    expect(spinValue(input)).toBe("3");
    expect(screen.getByText(/ripristinato/)).toBeTruthy();
  });

  it("valore valido: scrive il numero digitato", async () => {
    await mount(true, "downloads");
    setDownloadSlots.mockResolvedValue({ download_slots: 7 });
    const input = screen.getByRole("spinbutton");

    fireEvent.change(input, { target: { value: "7" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    expect(setDownloadSlots).toHaveBeenCalledWith(7);
    expect(screen.queryByText(/ripristinato/)).toBeNull();
  });

  it("il campo si riallinea quando il valore arriva da fuori (reload dopo il salvataggio di un altro campo)", async () => {
    await mount(true, "downloads");
    expect(spinValue(screen.getByRole("spinbutton"))).toBe("3");

    patchConfigSettings.mockResolvedValue({ ...CONFIG, slskd_download_dir: field("/Users/x/Downloads2"), download_slots: 8 });
    fireEvent.change(screen.getByDisplayValue("/Users/x/Downloads"), { target: { value: "/Users/x/Downloads2" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    });

    expect(spinValue(screen.getByRole("spinbutton"))).toBe("8");
  });

  it("il riallineamento dall'esterno non cancella quello che l'utente sta digitando", async () => {
    await mount(true, "downloads");
    const input = screen.getByRole("spinbutton");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "5" } });

    patchConfigSettings.mockResolvedValue({ ...CONFIG, slskd_download_dir: field("/Users/x/Downloads2"), download_slots: 8 });
    fireEvent.change(screen.getByDisplayValue("/Users/x/Downloads"), { target: { value: "/Users/x/Downloads2" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    });

    // il reload esterno (download_slots: 8) non deve stomp-are la digitazione in corso
    expect(spinValue(input)).toBe("5");

    setDownloadSlots.mockResolvedValue({ download_slots: 5 });
    await act(async () => {
      fireEvent.blur(input);
    });
    expect(setDownloadSlots).toHaveBeenCalledWith(5);
  });
});


describe("ConfigCard: note e provenienza dei campi", () => {
  it("una nota del backend su un campo valido resta visibile come hint", async () => {
    getConfigSettings.mockResolvedValue({ ...CONFIG, slskd_download_dir: { ...field("/Users/x/Downloads"), detail: "Nota: cartella non scrivibile" } });
    pickerAvailability.mockResolvedValue({ available: false });
    render(<ConfigCard section="downloads" />);
    await act(async () => {});
    expect(screen.getByText("Nota: cartella non scrivibile")).toBeTruthy();
  });

  it("un valore che sovrascrive backend/.env porta il badge «override .env»", async () => {
    getConfigSettings.mockResolvedValue({ ...CONFIG, library_root: { ...field("/Users/x/Music"), source: "db" } });
    pickerAvailability.mockResolvedValue({ available: false });
    render(<ConfigCard section="library" />);
    await act(async () => {});
    expect(screen.getByText("override .env")).toBeTruthy();
  });
});

describe("ConfigCard: bozze per sezione", () => {
  it("salvare Download conserva la bozza di Libreria e scrive solo i campi di Download", async () => {
    const view = await mount(false);
    fireEvent.change(screen.getByDisplayValue("/Users/x/Music"), { target: { value: "/Music/Draft" } });
    // Prima il positivo, così il null di sotto prova davvero che la sezione è nascosta.
    expect(screen.getByRole("textbox", { name: /Cartella della musica/ })).toBeTruthy();
    view.rerender(<ConfigCard section="downloads" />);
    expect(screen.queryByRole("textbox", { name: /Cartella della musica/ })).toBeNull();
    fireEvent.change(screen.getByDisplayValue("/Users/x/Downloads"), { target: { value: "/Downloads/New" } });
    patchConfigSettings.mockResolvedValue({ ...CONFIG, slskd_download_dir: field("/Downloads/New") });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Salva" })); });
    expect(patchConfigSettings).toHaveBeenCalledWith({ slskd_download_dir: "/Downloads/New" });
    view.rerender(<ConfigCard section="library" />);
    expect(screen.getByDisplayValue("/Music/Draft")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Salva" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("il salvataggio automatico degli slot non ricarica né cancella le cartelle in modifica", async () => {
    await mount(false, "downloads");
    fireEvent.change(screen.getByDisplayValue("/Users/x/Downloads"), { target: { value: "/Downloads/Draft" } });
    setDownloadSlots.mockResolvedValue({ download_slots: 5 });
    const slots = screen.getByRole("spinbutton");
    fireEvent.change(slots, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(slots); });
    expect(getConfigSettings).toHaveBeenCalledTimes(1);
    expect(screen.getByDisplayValue("/Downloads/Draft")).toBeTruthy();
  });

  it("un salvataggio fallito conserva la bozza e mostra l'errore", async () => {
    await mount(false);
    patchConfigSettings.mockRejectedValue(new Error("Save failed"));
    fireEvent.change(screen.getByDisplayValue("/Users/x/Music"), { target: { value: "/Music/Draft" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Salva" })); });
    expect(screen.getByRole("alert").textContent).toContain("Save failed");
    expect(screen.getByDisplayValue("/Music/Draft")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
