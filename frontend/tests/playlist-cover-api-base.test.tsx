import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

afterEach(cleanup);

/* La cover caricata dall'utente e' servita dal backend (`/api/playlists/{id}/artwork`).
   In sviluppo il proxy di Next la risolve; nel bundle desktop la pagina sta su
   tauri://localhost e il backend altrove: l'URL va premesso di API_BASE,
   altrimenti l'immagine non si carica. Gli URL assoluti di piattaforma restano
   com'erano. */

vi.mock("@/lib/api/base", () => ({ API_BASE: "http://127.0.0.1:8000" }));

describe("PlaylistCover e API_BASE", () => {
  it("premette API_BASE agli URL relativi del backend", async () => {
    const { PlaylistCover } = await import("@/components/playlist-cover");
    const { container } = render(<PlaylistCover artworkUrl="/api/playlists/7/artwork?v=1" kind="manual" />);
    expect(container.querySelector("img")?.getAttribute("src")).toBe("http://127.0.0.1:8000/api/playlists/7/artwork?v=1");
  });

  it("lascia stare gli URL assoluti di piattaforma", async () => {
    const { PlaylistCover } = await import("@/components/playlist-cover");
    const { container } = render(<PlaylistCover artworkUrl="https://i.scdn.co/x.jpg" kind="playlist" />);
    expect(container.querySelector("img")?.getAttribute("src")).toBe("https://i.scdn.co/x.jpg");
  });
});
