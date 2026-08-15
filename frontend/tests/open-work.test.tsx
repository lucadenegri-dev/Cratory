import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OpenWork, queuesActive } from "@/components/dashboard/open-work";
import type { DownloadStatus, PipelineStatus, Track } from "@/lib/api";

function dl(over: Partial<DownloadStatus> = {}): DownloadStatus {
  return {
    available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
    needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
    error: null, current_label: null, ...over,
  };
}

function track(over: Partial<Track> = {}): Track {
  return {
    id: 1, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
    title: "Tempo", artist: "Rrose", album: null, genre: null, year: null,
    duration_seconds: null, bpm: null, camelot_key: null, energy: null, label: null,
    status: "imported", url: null, isrc: null, playlists: [], added_at: "2026-08-14T10:00:00Z",
    playlist_added_at: null, spotify_url: null, album_art_url: null, has_local_file: false,
    local_path: null, local_format: null, local_bitrate: null, primary_file_id: null,
    genre_from_file: false, album_from_file: false, label_from_file: false, year_from_file: false,
    archived: false, rating: null, last_download_outcome: null, last_download_reason: null,
    last_download_path: null, ...over,
  };
}

const IDLE_PIPE = { download_active: false } as PipelineStatus;

describe("queuesActive", () => {
  it("è vera solo con download running o download_active in pipeline", () => {
    expect(queuesActive(dl({ status: "running" }), IDLE_PIPE)).toBe(true);
    expect(queuesActive(dl(), { ...IDLE_PIPE, download_active: true } as PipelineStatus)).toBe(true);
    expect(queuesActive(dl(), IDLE_PIPE)).toBe(false);
    expect(queuesActive(null, null)).toBe(false);
  });
});

describe("open work", () => {
  afterEach(cleanup);

  it("senza nulla di pendente dichiara il vuoto, nessuna riga numerata", () => {
    render(<OpenWork download={dl()} pending={[]} inboxFiles={0} leads={[]} />);
    expect(screen.getByText("Nessun lavoro aperto")).toBeTruthy();
    expect(screen.queryByText("01")).toBeNull();
  });

  it("download running: progressbar reale e traccia in lavorazione", () => {
    render(
      <OpenWork
        download={dl({ status: "running", processed: 3, total: 10, current_label: "Rrose — Tempo" })}
        pending={[]} inboxFiles={0} leads={[]}
      />,
    );
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("30");
    expect(screen.getByText("Rrose — Tempo")).toBeTruthy();
    expect(screen.getByText("Download in corso").closest("a")?.getAttribute("href")).toBe("/wishlist");
  });

  it("le righe si numerano in sequenza solo per le sezioni visibili", () => {
    render(
      <OpenWork
        download={dl()} pending={[track({ id: 9, title: "Ecco", artist: "AAAA" })]}
        inboxFiles={4} leads={[track({ id: 2 })]}
      />,
    );
    // Tre sezioni visibili (revisione, inbox, leads) numerate 01/02/03: il
    // download fermo non occupa il numero 01.
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("02")).toBeTruthy();
    expect(screen.getByText("03")).toBeTruthy();
    expect(screen.queryByText("04")).toBeNull();
    expect(screen.getByText("1 download da rivedere").closest("a")?.getAttribute("href")).toBe("/wishlist");
    expect(screen.getByText("4 file in inbox da sistemare").closest("a")?.getAttribute("href")).toBe("/organize/files");
  });

  it("i leads mostrano artista — titolo, fonte e data, e linkano la traccia", () => {
    render(<OpenWork download={null} pending={[]} inboxFiles={null} leads={[track()]} />);
    expect(screen.getByText(/Rrose — Tempo/).closest("a")?.getAttribute("href")).toBe("/tracks/1");
    expect(screen.getByText("spotify")).toBeTruthy();
  });

  it("needs_review conta anche senza lista pending (fallback dal job)", () => {
    render(<OpenWork download={dl({ needs_review: 2 })} pending={[]} inboxFiles={0} leads={[]} />);
    expect(screen.getByText("2 download da rivedere")).toBeTruthy();
  });
});
