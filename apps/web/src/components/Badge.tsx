import { labels } from "@/lib/labels";

const STATUS_STYLES: Record<string, string> = {
  watching: "bg-blue-500/10 text-blue-400 ring-blue-500/30",
  buy: "bg-accent/15 text-accent-strong ring-accent/30",
  auction: "bg-amber-500/10 text-amber-500 ring-amber-500/30",
  purchased: "bg-violet-500/10 text-violet-400 ring-violet-500/30",
  in_stock: "bg-violet-500/10 text-violet-400 ring-violet-500/30",
  listed_for_sale: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
  sold: "bg-accent/15 text-accent-strong ring-accent/30",
  abandoned: "bg-danger/10 text-danger ring-danger/30",
};

const DEFAULT_STYLE = "bg-border text-fg-muted ring-border";

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? DEFAULT_STYLE;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
    >
      {labels.opportunityStatus(status)}
    </span>
  );
}

export function ReferenceStatusBadge({ status }: { status: string }) {
  const style =
    status === "confirmed" || status === "corrected"
      ? "bg-accent/15 text-accent-strong ring-accent/30"
      : status === "unknown"
        ? "bg-danger/10 text-danger ring-danger/30"
        : "bg-amber-500/10 text-amber-500 ring-amber-500/30";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}
    >
      {labels.referenceStatus(status)}
    </span>
  );
}
