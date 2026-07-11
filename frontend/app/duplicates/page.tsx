"use client";

import { useCallback, useEffect, useState } from "react";
import { listDuplicates, setKeeper, dismissDuplicate, type DupGroup } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { DupGroupCard } from "@/components/dup-group";
import { Alert, EmptyState } from "@/components/ui";
import { useT } from "@/lib/i18n";

export default function DuplicatesPage() {
  const t = useT();
  const { scan } = useJobs();
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    listDuplicates()
      .then((g) => { setGroups(g); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); load(); }
    catch (e) { setActionError(e instanceof Error ? e.message : t.common.error); }
  };
  const onSetKeeper = (groupId: number, fileId: number) => act(() => setKeeper(groupId, fileId));
  const onDismiss = (groupId: number) => act(() => dismissDuplicate(groupId));

  const active = groups.filter((g) => !g.dismissed);
  const filesToRemove = active.reduce(
    (n, g) => n + g.members.filter((m) => m.action === "remove").length, 0,
  );
  const byMatch: Record<string, number> = {};
  for (const g of active) byMatch[g.match_kind] = (byMatch[g.match_kind] ?? 0) + 1;

  const ordered = [...active, ...groups.filter((g) => g.dismissed)];

  return (
    <PageLayout
      title="Duplicates"
      meta={t.duplicates.groupsCount(active.length)}
      marginaliaTitle={t.common.summary}
      marginalia={<Marginalia groups={active.length} filesToRemove={filesToRemove} byMatch={byMatch} />}
      guide={<>
        <p>{t.duplicates.guide1}</p>
        <p>{t.duplicates.guide2}</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>{t.common.backendOffline}</Alert>}
        {actionError && <Alert>{actionError}</Alert>}

        {groups.length === 0 && !offline ? (
          <EmptyState title={t.duplicates.emptyTitle}>{t.duplicates.emptyBody}</EmptyState>
        ) : (
          ordered.map((g) => (
            <DupGroupCard key={g.id} group={g} onSetKeeper={onSetKeeper} onDismiss={onDismiss} />
          ))
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ groups, filesToRemove, byMatch }: {
  groups: number;
  filesToRemove: number;
  byMatch: Record<string, number>;
}) {
  const t = useT();
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{groups}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{t.duplicates.statGroups}</div>
      </div>
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{filesToRemove}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{t.duplicates.filesToRemove}</div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.duplicates.byMatch}</div>
        <div className="flex flex-col gap-1">
          {Object.entries(byMatch).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
            <div key={k} className="flex justify-between"><span className="text-muted">{k}</span><span className="tnum text-fg">{n}</span></div>
          ))}
        </div>
      </div>
      <div className="text-[11px] text-ok">{t.duplicates.removalsNote(filesToRemove)}</div>
    </div>
  );
}
