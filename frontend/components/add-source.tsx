"use client";

import { useState } from "react";
import { addSource } from "@/lib/api";
import { Button, Input } from "./ui";

export function AddSource({ onAdded }: { onAdded: () => void }) {
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!path.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addSource(path.trim(), label.trim() || undefined);
      setPath("");
      setLabel("");
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Aggiungi radice</div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="/percorso/alla/cartella di musica…"
          className="sm:flex-1"
        />
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="etichetta"
          className="sm:w-40"
        />
        <Button onClick={submit} disabled={busy || !path.trim()}>+ Aggiungi</Button>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
