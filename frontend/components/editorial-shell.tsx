import type { ReactNode } from "react";
import { IndexNav } from "./index-nav";
import { JobsProvider } from "./jobs-provider";

export function EditorialShell({ children }: { children: ReactNode }) {
  return (
    <JobsProvider>
      <div className="min-h-screen lg:grid lg:grid-cols-[180px_1fr]">
        <aside className="border-b border-border lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <IndexNav />
        </aside>
        <main className="min-w-0" style={{ paddingBottom: "var(--player-bar-height, 0px)" }}>{children}</main>
      </div>
    </JobsProvider>
  );
}
