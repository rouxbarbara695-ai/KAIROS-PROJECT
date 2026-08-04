import { Card } from "@/components/Card";
import { Disclosure } from "@/components/Disclosure";
import { listPlatforms } from "@/lib/api";
import { formatAmount } from "@/lib/labels";
import { PlatformFeesForm } from "./PlatformFeesForm";

// Les grilles changent dès qu'on en saisit une : une page mise en cache
// afficherait des frais périmés, c'est-à-dire des profits faux.
export const dynamic = "force-dynamic";

function percent(rate: string | null | undefined): string {
  if (!rate) return "—";
  const value = Number(rate);
  if (!Number.isFinite(value)) return rate;
  return `${(value * 100).toFixed(2).replace(".", ",")} %`;
}

/** Ce que revendre coûte réellement : commission, TVA sur la commission et
 *  frais de paiement. Rendu `null` quand la TVA n'est pas renseignée — la
 *  taire donnerait un coût sous-estimé d'un cinquième de la commission, et
 *  c'est précisément ce qu'il faut voir. */
function resaleCost(rule: {
  seller_fee_rate?: string | null;
  seller_fee_vat_rate?: string | null;
  payment_fee_rate?: string | null;
}): string | null {
  const commission = Number(rule.seller_fee_rate ?? 0);
  if (!Number.isFinite(commission)) return null;
  if (commission > 0 && rule.seller_fee_vat_rate == null) return null;

  const vat = Number(rule.seller_fee_vat_rate ?? 0);
  const payment = Number(rule.payment_fee_rate ?? 0);
  if (!Number.isFinite(vat) || !Number.isFinite(payment)) return null;

  return percent(String(commission * (1 + vat) + payment));
}

export default async function PlatformsPage() {
  const platforms = await listPlatforms();
  const missing = platforms.filter((platform) => !platform.has_active_rule);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Plateformes</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Les frais entrent directement dans le profit et dans le prix maximal
          d&apos;achat. Aucune grille n&apos;est fournie par défaut : une
          commission inventée fausserait tous les calculs sans que rien ne le
          signale.
        </p>
      </div>

      {missing.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-amber-500">
            {missing.length} plateforme{missing.length > 1 ? "s" : ""} sans
            grille de frais
          </p>
          <p className="mt-1 text-sm text-fg-muted">
            Une opportunité issue de ces plateformes ne peut pas être analysée :
            ses coûts d&apos;achat ne peuvent pas être établis. Renseignez la
            grille depuis la page officielle des tarifs.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {platforms.map((platform) => {
          const rule = platform.active_rule;
          return (
            <Card key={platform.code}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold">{platform.name}</h2>
                <span
                  className={`text-xs ${
                    platform.has_active_rule
                      ? "text-accent-strong"
                      : "text-amber-500"
                  }`}
                >
                  {platform.has_active_rule
                    ? `Grille v${rule?.version}`
                    : "Aucune grille"}
                </span>
              </div>

              {rule && (
                <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
                  <div className="contents">
                    <dt className="text-fg-muted">Commission achat</dt>
                    <dd className="numeric">{percent(rule.buyer_fee_rate)}</dd>
                  </div>
                  <div className="contents">
                    <dt className="text-fg-muted">Commission vente</dt>
                    <dd className="numeric">
                      {percent(rule.seller_fee_rate)}
                      {rule.seller_fee_fixed
                        ? ` + ${formatAmount(rule.seller_fee_fixed, "EUR")}`
                        : ""}
                    </dd>
                  </div>
                  {rule.payment_fee_rate && (
                    <div className="contents">
                      <dt className="text-fg-muted">Frais de paiement</dt>
                      <dd className="numeric">{percent(rule.payment_fee_rate)}</dd>
                    </div>
                  )}
                  <div className="contents">
                    <dt className="text-fg-muted">Coût réel de revente</dt>
                    <dd className="numeric">
                      {resaleCost(rule) ?? (
                        <span className="text-amber-500">
                          TVA sur commission non renseignée
                        </span>
                      )}
                    </dd>
                  </div>
                  {rule.provenance_url && (
                    <div className="contents">
                      <dt className="text-fg-muted">Source</dt>
                      <dd className="break-all">{rule.provenance_url}</dd>
                    </div>
                  )}
                </dl>
              )}

              <div className="mt-3">
                <Disclosure
                  summary={
                    rule ? "Enregistrer une nouvelle version" : "Saisir la grille"
                  }
                >
                  <PlatformFeesForm
                    code={platform.code}
                    name={platform.name}
                    current={
                      rule
                        ? {
                            buyerFeeRate: rule.buyer_fee_rate,
                            buyerFeeFixed: rule.buyer_fee_fixed,
                            sellerFeeRate: rule.seller_fee_rate,
                            sellerFeeFixed: rule.seller_fee_fixed,
                            sellerFeeMin: rule.seller_fee_min,
                            sellerFeeMax: rule.seller_fee_max,
                            buyerFeeVatRate: rule.buyer_fee_vat_rate,
                            sellerFeeVatRate: rule.seller_fee_vat_rate,
                            paymentFeeRate: rule.payment_fee_rate,
                            sellerFeeBasis: rule.seller_fee_basis,
                            sellerFeeTiers: rule.seller_fee_tiers,
                            provenanceUrl: rule.provenance_url,
                          }
                        : null
                    }
                  />
                </Disclosure>
              </div>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-fg-muted">
        Une grille n&apos;est jamais réécrite : enregistrer une nouvelle version
        ferme la précédente. Une analyse produite sous l&apos;ancienne grille
        reste rejouable. Saisir des tarifs n&apos;autorise aucune collecte
        automatisée — c&apos;est une validation distincte.
      </p>
    </div>
  );
}
