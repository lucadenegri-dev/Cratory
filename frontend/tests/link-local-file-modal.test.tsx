import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkLocalFileModal } from "@/components/link-local-file-modal";

const searchLocalFiles = vi.fn();
const linkLocalFile = vi.fn();
const pickerAvailability = vi.fn();
const pickPath = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  searchLocalFiles: (...a: unknown[]) => searchLocalFiles(...a),
  linkLocalFile: (...a: unknown[]) => linkLocalFile(...a),
  pickerAvailability: (...a: unknown[]) => pickerAvailability(...a),
  pickPath: (...a: unknown[]) => pickPath(...a),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const TARGET = { id: 5, artist: "Objekt", title: "Ganzfeld" };

async function mount(available: boolean) {
  pickerAvailability.mockResolvedValue({ available });
  await act(async () => {
    render(<LinkLocalFileModal target={TARGET} onClose={() => {}} onLinked={() => {}} />);
  });
}

describe("LinkLocalFileModal + picker", () => {
  it("con picker disponibile il percorso esatto ha Sfoglia", async () => {
    await mount(true);
    expect(screen.getByRole("button", { name: "Sfoglia…" })).toBeTruthy();
  });

  it("senza picker niente Sfoglia (resta l'input testuale)", async () => {
    await mount(false);
    expect(screen.queryByRole("button", { name: "Sfoglia…" })).toBeNull();
  });

  it("il file scelto riempie il percorso esatto senza collegare subito", async () => {
    // linkLocalFile mai chiamata = pinna anche il type=\"button\" del pulsante
    // (un submit del form partirebbe col percorso vuoto).
    await mount(true);
    pickPath.mockResolvedValue({ path: "/Users/x/Downloads/track.mp3" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sfoglia…" }));
    });
    expect(screen.getByDisplayValue("/Users/x/Downloads/track.mp3")).toBeTruthy();
    expect(linkLocalFile).not.toHaveBeenCalled();
  });

  it("annullo del dialog: il percorso esatto resta vuoto", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: null });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sfoglia…" }));
    });
    expect(screen.queryByDisplayValue("/Users/x/Downloads/track.mp3")).toBeNull();
    expect(linkLocalFile).not.toHaveBeenCalled();
  });
});
