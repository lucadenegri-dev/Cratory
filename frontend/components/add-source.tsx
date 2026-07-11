"use client";

import { useState } from "react";
import { addSource } from "@/lib/api";
import { Button, Input } from "./ui";
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
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={t.sources.pathPlaceholder}
          className="sm:flex-1"
        />
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={t.sources.labelPlaceholder}
          className="sm:w-40"
        />
        <Button onClick={submit} disabled={busy || !path.trim()}>{t.sources.addButton}</Button>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
