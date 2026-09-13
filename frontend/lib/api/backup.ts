import { apiDelete, apiGet, apiPost } from "./client";

/** `file` è il numero di file della voce: le cover sono tante, le altre una
    sola (0 quando mancano). */
export type BackupVoce = { nome: string; byte: number; presente: boolean; file: number };
export type BackupEstimate = {
  byte: number;
  voci: BackupVoce[];
  last_backup_at: string | null;
  nome_di_default: string;
  picker_disponibile: boolean;
};
export type BackupResult = { percorso: string; byte: number; creato_il: string };
export type RestoreSummary = {
  creato_il: string | null;
  app_version: string | null;
  tracce: number;
  playlist: number;
  membri: string[];
  ha_credenziali: boolean;
};
export type RestoreOutcome = {
  stato: "ok" | "fallito";
  applicato_il: string;
  motivo?: string | null;
  backup_creato_il?: string | null;
  backup_app_version?: string | null;
  tracce?: number | null;
  playlist?: number | null;
};

export function getBackupEstimate() {
  return apiGet<BackupEstimate>("/api/backup/estimate");
}

/** `path` nullo = il backend salva in ~/Downloads col nome di default. */
export function createBackup(path: string | null) {
  return apiPost<BackupResult>("/api/backup", { path });
}

export function prepareRestore(path: string) {
  return apiPost<RestoreSummary>("/api/backup/restore/prepare", { path });
}

export function confirmRestore() {
  return apiPost<{ riavvio_necessario: boolean }>("/api/backup/restore/confirm");
}

export function cancelRestore() {
  return apiDelete<void>("/api/backup/restore");
}

export function lastRestore() {
  return apiGet<RestoreOutcome | null>("/api/backup/restore/last");
}
