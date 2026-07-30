import Link from "next/link";
import { Card, EmptyState } from "@/components/Card";
import {
  getMe,
  getPortfolioOverview,
  getStrategy,
  listPlatforms,
} from "@/lib/api";
import { formatAmount, formatDateTime, labels } from "@/lib/labels";
import { MovementForm } from "./MovementForm";
import { StrategyForm } from "./StrategyForm";

// Le registre change à chaque saisie : une page mise en cache afficherait une
// trésorerie périmée, c'est-à-dire exactement le défaut qu'on cherche à éviter
// en la recalculant depuis les mouvements.
export const dynamic = "force-dynamic";

/** Natures qui augmentent la trésorerie, pour l'affichage du signe. */
const CREDITS = new Set([
  "capital_contribution",
  "sale_receipt",
  "refund",
  "positive_adjustment",
]);

function share(part: string, whole: string): string {
  const numerator = Number(part);
  const denominator = Number(whole);
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator)) return "—";
  if (denominator <= 0) return "—";
  return `${((numerator / denominator) * 100).toFixed(1).replace(".", ",")} %`;
}

export default async function PortfolioPage() {
  const me = await getMe();
  const portfolioId = me.portfolio_ids[0];

  if (!portfolioId) {
    // Le mandataire de développement en crée un au premier appel, mais un
    // principal réel pourrait n'en avoir aucun : mieux vaut le dire que
    // planter sur un identifiant absent.
    return (
      <EmptyState
        title="Aucun portefeuille"
        description="Ce compte n'est rattaché à aucun portefeuille."
      />
    );
  }

  const [overview, strategy, platforms] = await Promise.all([
    getPortfolioOverview(portfolioId),
    getStrategy(portfolioId),
    listPlatforms(),
  ]);

  const immobilization = share(
    overview.stock_at_cost_eur,
    overview.total_capital_eur,
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Portefeuille</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Trésorerie reconstruite depuis les mouvements, stock valorisé au coût
          d&apos;acquisition.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-xs text-fg-muted">Trésorerie disponible</p>
          <p className="numeric mt-1 text-xl font-semibold text-accent-strong">
            {formatAmount(overview.available_cash_eur, "EUR")}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-fg-muted">Stock au coût</p>
          <p className="numeric mt-1 text-xl font-semibold">
            {formatAmount(overview.stock_at_cost_eur, "EUR")}
          </p>
          <p className="mt-1 text-xs text-fg-muted">
            {immobilization} du capital immobilisé
          </p>
        </Card>
        <Card>
          <p className="text-xs text-fg-muted">Capital total</p>
          <p className="numeric mt-1 text-xl font-semibold">
            {formatAmount(overview.total_capital_eur, "EUR")}
          </p>
        </Card>
      </div>

      {/* La stratégie décide où l'on revend et à quelles conditions : elle
          gouverne le prix maximal et le verdict, elle vient donc avant le
          détail des mouvements. */}
      <Card>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-fg-muted">Stratégie</h2>
          <span className="text-xs text-fg-muted">version {strategy.version}</span>
        </div>
        <StrategyForm
          portfolioId={portfolioId}
          platforms={platforms.map((platform) => ({
            code: platform.code,
            name: platform.name,
            hasRule: platform.has_active_rule,
          }))}
          current={{
            minimumRoi: strategy.minimum_roi,
            minimumProfitEur: strategy.minimum_profit_eur,
            maximumAllocationRate: strategy.maximum_allocation_rate,
            negotiationBuffer: strategy.negotiation_buffer,
            resalePlatformCode: strategy.resale_platform_code ?? null,
          }}
        />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-fg-muted">
          Ajouter un mouvement
        </h2>
        <MovementForm portfolioId={portfolioId} />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-fg-muted">
          Montres en stock
        </h2>
        {overview.holdings.length === 0 ? (
          <p className="text-sm text-fg-muted">
            Aucune montre en stock. Le capital immobilisé est nul.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-fg-muted">
                  <th className="pb-1.5 pr-4 font-normal">Montre</th>
                  <th className="pb-1.5 pr-4 font-normal">Coût d&apos;achat</th>
                  <th className="pb-1.5 font-normal">Acquise le</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {overview.holdings.map((holding) => (
                  <tr key={holding.opportunity_id}>
                    <td className="py-1.5 pr-4">
                      <Link
                        href={`/opportunities/${holding.opportunity_id}`}
                        className="hover:text-accent-strong"
                      >
                        {holding.brand ?? "—"} {holding.reference ?? ""}
                      </Link>
                    </td>
                    <td className="numeric py-1.5 pr-4">
                      {formatAmount(holding.cost_eur, "EUR")}
                    </td>
                    <td className="py-1.5 text-fg-muted">
                      {formatDateTime(holding.purchased_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-fg-muted">
          Mouvements de trésorerie
        </h2>
        {overview.movements.length === 0 ? (
          <EmptyState
            title="Aucun mouvement"
            description="Commencez par enregistrer votre capital de départ."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-fg-muted">
                  <th className="pb-1.5 pr-4 font-normal">Date</th>
                  <th className="pb-1.5 pr-4 font-normal">Nature</th>
                  <th className="pb-1.5 pr-4 font-normal">Montant</th>
                  <th className="pb-1.5 font-normal">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {overview.movements.map((movement) => {
                  const credit = CREDITS.has(movement.kind);
                  return (
                    <tr key={movement.id}>
                      <td className="py-1.5 pr-4 text-fg-muted">
                        {formatDateTime(movement.occurred_at)}
                      </td>
                      <td className="py-1.5 pr-4">
                        {labels.ledgerKind(movement.kind)}
                      </td>
                      <td
                        className={`numeric py-1.5 pr-4 ${
                          credit ? "text-accent-strong" : "text-danger"
                        }`}
                      >
                        {credit ? "+" : "−"}
                        {formatAmount(movement.amount_eur, "EUR")}
                      </td>
                      <td className="py-1.5 text-fg-muted">
                        {movement.notes ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
