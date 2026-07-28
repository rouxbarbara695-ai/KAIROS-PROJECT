import type { AuditEventResponse } from "@/lib/api";
import { formatDateTime, labels } from "@/lib/labels";

/**
 * Rend une charge d'audit sans supposer sa forme : `before_data` et
 * `after_data` sont du JSON libre, et une clé masquée côté API (`***`) doit
 * rester visible en tant que telle — la trace montre qu'une valeur existe,
 * sans la divulguer.
 */
function PayloadPreview({ payload }: { payload: unknown }) {
  if (payload === null || payload === undefined) return null;
  if (typeof payload !== "object") {
    return <span className="numeric">{String(payload)}</span>;
  }

  const entries = Object.entries(payload as Record<string, unknown>);
  if (entries.length === 0) return null;

  return (
    <dl className="grid gap-x-3 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-fg-muted">{key}</dt>
          <dd className="numeric break-all">
            {typeof value === "object" && value !== null
              ? JSON.stringify(value)
              : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function AuditTrail({ events }: { events: AuditEventResponse[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-fg-muted">
        Aucune correction pour l&rsquo;instant. Chaque correction sera tracée
        ici, avec son motif, et ne pourra plus être modifiée.
      </p>
    );
  }

  return (
    <ol className="space-y-4">
      {events.map((event) => (
        <li
          key={event.id}
          className="border-l-2 border-border pl-4 [&:last-child]:pb-0"
        >
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-sm font-medium">
              {labels.auditAction(event.action)}
            </span>
            <span className="rounded-full bg-border px-2 py-0.5 text-[11px] text-fg-muted">
              {labels.auditResource(event.resource_type)}
            </span>
            <span className="text-xs text-fg-muted">
              {formatDateTime(event.occurred_at)}
            </span>
          </div>

          <p className="mt-1 text-sm">{event.reason}</p>

          {(event.before_data || event.after_data) && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-fg-muted hover:text-fg">
                Avant / après
              </summary>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wide text-fg-muted">
                    Avant
                  </p>
                  <PayloadPreview payload={event.before_data} />
                </div>
                <div>
                  <p className="mb-1 text-[11px] uppercase tracking-wide text-fg-muted">
                    Après
                  </p>
                  <PayloadPreview payload={event.after_data} />
                </div>
              </div>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}
