import { notFound } from "next/navigation";
import { Card } from "@/components/Card";
import { StatusBadge, ReferenceStatusBadge } from "@/components/Badge";
import { ApiError, getOpportunity, listOpportunityEvents } from "@/lib/api";
import { formatAmount, labels } from "@/lib/labels";
import { Disclosure } from "@/components/Disclosure";
import { AuditTrail } from "./AuditTrail";
import {
  PriceInputForm,
  SellerProfileForm,
  WatchProfileForm,
} from "./CorrectionForms";
import { ComparablesPanel } from "./ComparablesPanel";
import { ValuationPanel } from "./ValuationPanel";
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

  const events = await listOpportunityEvents(id);

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
              ? `${labels.sourceMode(opportunity.source_mode)} — ${opportunity.manual_identifier}`
              : labels.sourceMode(opportunity.source_mode)}
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
                ? formatAmount(
                    opportunity.latest_price.amount,
                    opportunity.latest_price.currency,
                  )
                : "sur demande"
            }
          />
          <DetailRow
            label="Équivalent EUR"
            value={formatAmount(opportunity.latest_price?.amount_eur, "EUR")}
          />
          {opportunity.latest_price?.missing_reason && (
            <p className="mt-2 text-xs text-warning">
              {opportunity.latest_price.missing_reason}
            </p>
          )}
          <div className="mt-4">
            <Disclosure summary="Ajouter un relevé de prix">
              <PriceInputForm opportunityId={opportunity.id} />
            </Disclosure>
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            État et set
          </h2>
          <DetailRow
            label="Mécanique"
            value={labels.mechanicalCondition(
              opportunity.watch.condition_data.mechanical as string | undefined,
            )}
          />
          <DetailRow
            label="Cosmétique"
            value={labels.cosmeticCondition(
              opportunity.watch.condition_data.cosmetic as string | undefined,
            )}
          />
          <DetailRow
            label="Complétude"
            value={labels.completenessLevel(
              opportunity.watch.completeness_data.level as string | undefined,
            )}
          />
          <div className="mt-4">
            <Disclosure summary="Corriger l'état et le set">
              <WatchProfileForm
                opportunityId={opportunity.id}
                current={{
                  mechanical: opportunity.watch.condition_data.mechanical as
                    | string
                    | undefined,
                  cosmetic: opportunity.watch.condition_data.cosmetic as
                    | string
                    | undefined,
                  completeness: opportunity.watch.completeness_data.level as
                    | string
                    | undefined,
                }}
              />
            </Disclosure>
          </div>
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
                value={labels.sellerType(opportunity.seller.seller_type)}
              />
            </>
          ) : (
            <p className="text-sm text-fg-muted">
              Aucune information vendeur.
            </p>
          )}
          <div className="mt-4">
            <Disclosure summary="Corriger le vendeur">
              <SellerProfileForm
                opportunityId={opportunity.id}
                current={{
                  countryCode: opportunity.seller?.country_code,
                  sellerType: opportunity.seller?.seller_type,
                }}
              />
            </Disclosure>
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-fg-muted">
            Cote de marché
          </h2>
          <ValuationPanel opportunityId={opportunity.id} />
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

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-fg-muted">
          Comparables
        </h2>
        <ComparablesPanel
          opportunityId={opportunity.id}
          referenceConfirmed={["confirmed", "corrected"].includes(
            opportunity.watch.reference_status,
          )}
        />
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold text-fg-muted">
          Historique et audit
        </h2>
        <AuditTrail events={events.items} />
      </Card>
    </div>
  );
}
