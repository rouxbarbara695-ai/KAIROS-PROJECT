import { notFound } from "next/navigation";
import { Card } from "@/components/Card";
import { StatusBadge, ReferenceStatusBadge } from "@/components/Badge";
import { ApiError, getOpportunity } from "@/lib/api";
import { ReferenceConfirmationForm } from "./ReferenceConfirmationForm";

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2.5 text-sm last:border-0">
      <span className="text-fg-muted">{label}</span>
      <span className="numeric font-medium">{value}</span>
    </div>
  );
}

export default async function OpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let opportunity;
  try {
    opportunity = await getOpportunity(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              {opportunity.watch.brand} {opportunity.watch.reference}
            </h1>
            <ReferenceStatusBadge status={opportunity.watch.reference_status} />
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            {opportunity.source_mode === "manual"
              ? `Saisie manuelle — ${opportunity.manual_identifier}`
              : "Annonce en ligne"}
          </p>
        </div>
        <StatusBadge status={opportunity.status} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            Prix
          </h2>
          <DetailRow
            label="Prix courant"
            value={
              opportunity.latest_price?.amount
                ? `${opportunity.latest_price.amount} ${opportunity.latest_price.currency}`
                : "sur demande"
            }
          />
          <DetailRow
            label="Équivalent EUR"
            value={opportunity.latest_price?.amount_eur ?? "—"}
          />
          {opportunity.latest_price?.missing_reason && (
            <p className="mt-2 text-xs text-warning">
              {opportunity.latest_price.missing_reason}
            </p>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            État et set
          </h2>
          <DetailRow
            label="Mécanique"
            value={String(opportunity.watch.condition_data.mechanical ?? "—")}
          />
          <DetailRow
            label="Cosmétique"
            value={String(opportunity.watch.condition_data.cosmetic ?? "—")}
          />
          <DetailRow
            label="Complétude"
            value={String(opportunity.watch.completeness_data.level ?? "—")}
          />
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            Vendeur
          </h2>
          {opportunity.seller ? (
            <>
              <DetailRow
                label="Pays"
                value={opportunity.seller.country_code ?? "—"}
              />
              <DetailRow
                label="Type"
                value={opportunity.seller.seller_type ?? "—"}
              />
            </>
          ) : (
            <p className="text-sm text-fg-muted">
              Aucune information vendeur.
            </p>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            Analyse
          </h2>
          <p className="text-sm text-fg-muted">
            Aucune analyse : les moteurs de valorisation, pricing et score
            arrivent avec l&rsquo;Epic 2/3.
          </p>
        </Card>
      </div>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-fg-muted">
          Confirmer la référence
        </h2>
        <ReferenceConfirmationForm
          opportunityId={opportunity.id}
          currentStatus={opportunity.watch.reference_status}
          referenceId={opportunity.watch.reference_id ?? null}
        />
      </Card>
    </div>
  );
}
