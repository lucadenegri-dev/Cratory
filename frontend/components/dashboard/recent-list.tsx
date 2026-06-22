import Link from "next/link";

export type RecentItem = { n: string; title: string; meta: string; href: string };

/** Lista numerata editoriale (set/playlist recenti). */
export function RecentList({ items, empty }: { items: RecentItem[]; empty: string }) {
  if (items.length === 0) return <p className="text-xs text-faint">{empty}</p>;
  return (
    <div>
      {items.map((it) => (
        <Link
          key={it.href}
          href={it.href}
          className="flex items-baseline gap-2 border-b border-border/60 py-1.5 last:border-0"
        >
          <span className="tnum text-xs text-faint">{it.n}</span>
          <span className="min-w-0 flex-1 truncate text-fg hover:text-fg-strong">{it.title}</span>
          <span className="tnum shrink-0 text-[10px] text-muted">{it.meta}</span>
        </Link>
      ))}
    </div>
  );
}
