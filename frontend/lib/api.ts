// Barrel: mantiene `@/lib/api` come punto d'importazione unico per tutte le
// pagine. L'implementazione vive in `./api/*` (B21 - split per dominio).
export * from "./api/client";
export * from "./api/types";
export * from "./api/format";
export * from "./api/tracks";
export * from "./api/playlists";
export * from "./api/sets";
export * from "./api/discovery";
export * from "./api/downloads";
export * from "./api/shazam";
export * from "./api/analysis";
export * from "./api/misc";
export * from "./api/slskd";
export * from "./api/settings";
export * from "./api/transitions";
