"use client";

import { useState } from "react";
import { addSource } from "@/lib/api";
import { Button, Input, Spinner } from "./ui";
import { useT } from "@/lib/i18n";

export function AddSource({ onAdded }: { onAdded: () => void }) {
  const t = useT();
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
      setError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.sources.addRoot}</div>
      {/* path su riga propria a piena larghezza: dev'essere leggibile per intero */}
      <div className="flex flex-col gap-2">
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={t.sources.pathPlaceholder}
          className="w-full"
        />
        <div className="flex gap-2">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={t.sources.labelPlaceholder}
            className="flex-1"
          />
          <Button onClick={submit} disabled={busy || !path.trim()}>{busy ? <Spinner /> : t.sources.addButton}</Button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
