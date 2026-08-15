"use client";

import { useEffect, useState } from "react";
import {
  apiGet, getLabels,
  type LabelStats, type LibraryStats,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { StatisticsView } from "@/components/statistics/statistics-view";

/** Route thin: carica stats e label, poi delega tutto alla vista. */
export default function StatisticsPage() {
  const t = useT();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<LibraryStats>("/api/stats").then(setStats).catch((e) => setError(String(e.message ?? e)));
    getLabels().then(setLabels).catch(() => {});
  }, []);

  return (
    <PageLayout title={t.stats.title}>
      {error && <div className="mb-6"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}
      {!stats && !error && <Loading />}
      {stats && <StatisticsView stats={stats} labels={labels} />}
    </PageLayout>
  );
}
