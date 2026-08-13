import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<Record<string, unknown>>();
  return {
    ...mod,
    updateTrack: vi.fn().mockResolvedValue({}),
    apiGet: vi.fn().mockResolvedValue({ id: 1 }),
    trackCoverSrc: () => null,
  };
});
vi.mock("@/lib/organize/api", () => ({
  updateFileTags: vi.fn().mockResolvedValue({}),
}));

import { apiGet, updateTrack } from "@/lib/api";
import { updateFileTags } from "@/lib/organize/api";
import { TrackEditModal } from "@/components/track-edit-modal";
import { it as itDict } from "@/lib/i18n/it";

function makeTrack(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, title: "T", artist: "A", album: null, genre: "Pop", year: 2001,
    bpm: 128, camelot_key: "8A", label: null, rating: null,
    primary_file_id: null, genre_from_file: false, album_from_file: false,
    label_from_file: false, year_from_file: false,
    playlists: [], has_local_file: false, spotify_id: null, soundcloud_id: null,
    source_type: "spotify", platform: null, duration_seconds: 300, energy: null,
    status: "ready_for_set", url: null, isrc: null, added_at: null,
    playlist_added_at: null, spotify_url: null, album_art_url: null,
    local_path: null, local_format: null, local_bitrate: null, archived: false,
    last_download_outcome: null, last_download_reason: null, last_download_path: null,
    ...overrides,
  } as never;
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("TrackEditModal — routing del salvataggio", () => {
  it("traccia posseduta: genre va sul file via Organize, non sulla Track", async () => {
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "Techno" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateFileTags).toHaveBeenCalledWith(42, { genre: "Techno" }));
    expect(updateTrack).not.toHaveBeenCalled();
    expect(apiGet).toHaveBeenCalledWith("/api/tracks/1"); // refresh degli effettivi
  });

  it("traccia posseduta: bpm resta sulla Track", async () => {
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("128"), { target: { value: "130" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateTrack).toHaveBeenCalledWith(1, { bpm: 130 }));
    expect(updateFileTags).not.toHaveBeenCalled();
  });

  it("lead senza file: genre va sulla Track come oggi", async () => {
    render(<TrackEditModal track={makeTrack()} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "House" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateTrack).toHaveBeenCalledWith(1, { genre: "House" }));
    expect(updateFileTags).not.toHaveBeenCalled();
  });
});

describe("TrackEditModal — indipendenza degli errori tra i due percorsi (C5)", () => {
  it("updateFileTags fallisce: updateTrack viene chiamato comunque e il modal resta aperto", async () => {
    vi.mocked(updateFileTags).mockRejectedValueOnce(new Error("boom"));
    const onClose = vi.fn();
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={onClose} onSaved={() => {}} />);
    // genre (campo file) e bpm (campo track) cambiano insieme: due patch indipendenti.
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "Techno" } });
    fireEvent.change(screen.getByDisplayValue("128"), { target: { value: "130" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);

    // Il percorso file fallisce ma non deve impedire l'invio del percorso track:
    // sono due try/catch indipendenti, non un blocco unico che si ferma al primo errore.
    await waitFor(() => expect(updateTrack).toHaveBeenCalledWith(1, { bpm: 130 }));
    await waitFor(() => expect(screen.getByText(/Tag file/)).toBeTruthy());
    // L'utente non deve perdere le modifiche: il modal non si chiude quando c'è un errore.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("entrambi i percorsi falliscono: il messaggio riporta entrambi i prefissi", async () => {
    vi.mocked(updateFileTags).mockRejectedValueOnce(new Error("file down"));
    vi.mocked(updateTrack).mockRejectedValueOnce(new Error("track down"));
    const onClose = vi.fn();
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={onClose} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "Techno" } });
    fireEvent.change(screen.getByDisplayValue("128"), { target: { value: "130" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);

    await waitFor(() => {
      const alert = screen.getByText(new RegExp(itDict.tracks.fileTagsErrorPrefix));
      expect(alert.textContent).toContain(itDict.tracks.fileTagsErrorPrefix);
      expect(alert.textContent).toContain(itDict.tracks.trackErrorPrefix);
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});
