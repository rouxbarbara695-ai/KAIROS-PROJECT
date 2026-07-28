import Link from "next/link";
import { Card, EmptyState } from "@/components/Card";
import { StatusBadge, ReferenceStatusBadge } from "@/components/Badge";
import { listOpportunities } from "@/lib/api";
import { formatAmount, labels } from "@/lib/labels";

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ brand?: string; status?: string }>;
}) {
  const params = await searchParams;
  const page = await listOpportunities({
    brand: params.brand,
    status: params.status,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Opportunités
          </h1>
          <p className="mt-1 text-sm text-fg-muted">
            {page.items.length} opportunité{page.items.length > 1 ? "s" : ""}{" "}
            en veille
          </p>
        </div>
        <form className="flex gap-2" action="/opportunities">
          <input
            type="text"
            name="brand"
            defaultValue={params.brand}
            placeholder="Filtrer par marque"
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
        </form>
      </div>

      {page.items.length === 0 ? (
        <EmptyState
          title="Aucune opportunité"
          description="Créez votre première opportunité manuellement, sans collecteur externe."
          action={
            <Link
              href="/opportunities/new"
              className="inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-bg"
            >
              Nouvelle opportunité
            </Link>
          }
        />
      ) : (
        <div className="grid gap-3">
          {page.items.map((opportunity) => (
            <Link
              key={opportunity.id}
              href={`/opportunities/${opportunity.id}`}
            >
              <Card className="transition-colors hover:border-accent/40 hover:bg-surface-hover">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium">
                        {opportunity.watch.brand ?? "Marque inconnue"}{" "}
                        {opportunity.watch.reference}
                      </p>
                      <ReferenceStatusBadge
                        status={opportunity.watch.reference_status}
                      />
                    </div>
                    <p className="mt-1 text-sm text-fg-muted">
                      {opportunity.source_mode === "manual"
                        ? opportunity.manual_identifier
                        : labels.sourceMode(opportunity.source_mode)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {opportunity.latest_price?.amount ? (
                      <span className="numeric text-sm">
                        {formatAmount(
                          opportunity.latest_price.amount,
                          opportunity.latest_price.currency,
                        )}
                      </span>
                    ) : (
                      <span className="text-sm text-fg-muted">
                        prix sur demande
                      </span>
                    )}
                    <StatusBadge status={opportunity.status} />
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
