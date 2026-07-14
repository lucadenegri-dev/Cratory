"use client";

import { fmtDate, type ScanRoot } from "@/lib/api";
import { useJobs } from "./jobs-provider";
import { Button, Spinner } from "./ui";
import { useT } from "@/lib/i18n";

export function SourcesTable({
  roots, onScan, onDelete, deletingId,
}: {
  roots: ScanRoot[];
  onScan: () => void;
  onDelete: (id: number) => void;
  deletingId: number | null;
}) {
  const t = useT();
  const { scan } = useJobs();
  const running = scan.status === "running";

  return (
    <div className="flex flex-col gap-4">
      <div className="border border-border">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
              <th className="px-3 py-2 font-normal">{t.sources.colPath}</th>
              <th className="px-3 py-2 font-normal">{t.sources.colLabel}</th>
              <th className="px-3 py-2 text-right font-normal">{t.sources.colFiles}</th>
              <th className="px-3 py-2 font-normal">{t.sources.colLastScan}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {roots.map((r) => (
              <tr key={r.id} className="border-b border-surface-2 last:border-0">
                <td className="px-3 py-2 text-fg-strong">{r.path}</td>
                <td className="px-3 py-2 text-muted">{r.label || t.common.empty}</td>
                <td className="tnum px-3 py-2 text-right text-fg">
                  {r.file_count}
                  {r.missing_count > 0 && (
                    <span className="block text-[10px] text-faint">{t.sources.missingCount(r.missing_count)}</span>
                  )}
                </td>
                <td className="px-3 py-2 text-muted">{fmtDate(r.last_scanned_at)}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => onDelete(r.id)}
                    aria-label={t.sources.removeRoot}
                    disabled={deletingId === r.id}
                    className="text-faint transition-colors hover:text-danger disabled:opacity-40 disabled:cursor-not-allowed"
                  >×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Il progresso dello scan è nella barra globale in basso (jobs-provider):
          qui solo il bottone (disabilitato mentre gira), niente meter doppio. */}
      <div>
        <Button onClick={onScan} disabled={running || roots.length === 0}>
          {running && <Spinner />}{running ? t.sources.scanning : t.sources.scanButton}
        </Button>
        {scan.status === "error" && (
          <p className="mt-2 text-xs text-danger">{t.sources.scanFailed(scan.error ?? "")}</p>
        )}
      </div>
    </div>
  );
}
