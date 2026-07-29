"use client";

import { useEffect, useState, useTransition } from "react";
import {
  ApiError,
  createAnalysis,
  getLatestAnalysis,
  type AnalysisResponse,
} from "@/lib/api";
import { formatAmount, formatDateTime, labels } from "@/lib/labels";

/** Poids des piliers (scoring-engine.md § 1), pour situer chaque note. */
const PILLAR_WEIGHTS: Record<string, string> = {
  profitability: "30 pts",
  liquidity: "27,5 pts",
  portfolio: "20 pts",
  condition: "15 pts",
  evidence_quality: "7,5 pts",
};

const PILLAR_SUBSCORES: Record<string, string[]> = {
  profitability: ["profit", "roi"],
  liquidity: ["delay", "depth", "consistency"],
  portfolio: ["cash_impact", "diversification", "immobilization"],
  condition: ["mechanical", "cosmetic", "completeness", "originality"],
  evidence_quality: ["listing", "comparables", "seller", "protections"],
};

const VERDICT_TONE: Record<string, string> = {
  buy: "border-accent/40 bg-accent/5 text-accent-strong",
  watch: "border-amber-500/40 bg-amber-500/5 text-amber-500",
  pass: "border-danger/40 bg-danger/5 text-danger",
  analysis_impossible: "border-border bg-surface-hover text-fg-muted",
};

const GATE_TONE: Record<string, string> = {
  passed: "text-accent-strong",
  passed_with_warning: "text-amber-500",
  failed: "text-danger",
  not_evaluated: "text-fg-muted",
};

type Gate = {
  code: string;
  status: string;
  reason_codes: string[];
  blocking: boolean;
};

type Scenario = {
  sale_price_eur: string;
  total_cost_before_sale_eur: string;
  net_profit_eur: string;
  roi: string | null;
};

function percent(rate: string | undefined): string {
  if (!rate) return "—";
  const value = Number(rate);
  if (!Number.isFinite(value)) return rate;
  return `${(value * 100).toFixed(1).replace(".", ",")} %`;
}

function ScoreBar({ value }: { value: number }) {
  const tone =
    value >= 70 ? "bg-accent" : value >= 55 ? "bg-amber-500" : "bg-danger";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
      <div
        className={`h-full rounded-full ${tone}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

function Pillar({
  name,
  value,
  subscores,
}: {
  name: string;
  value: string;
  subscores: Record<string, string>;
}) {
  const keys = PILLAR_SUBSCORES[name] ?? [];
  return (
    <div className="space-y-1.5 py-2">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span>
          {labels.pillar(name)}{" "}
          <span className="text-xs text-fg-muted">{PILLAR_WEIGHTS[name]}</span>
        </span>
        <span className="numeric font-medium">
          {Number(value).toFixed(1).replace(".", ",")}
        </span>
      </div>
      <ScoreBar value={Number(value)} />
      {keys.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-fg-muted">
          {keys.map((key) =>
            subscores[key] === undefined ? null : (
              <li key={key}>
                {labels.subscore(key)}{" "}
                <span className="numeric text-fg">
                  {Number(subscores[key]).toFixed(0)}
                </span>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}

export function AnalysisPanel({ opportunityId }: { opportunityId: string }) {
  const [isPending, startTransition] = useTransition();
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getLatestAnalysis(opportunityId)
      .then((latest) => {
        if (!cancelled) setAnalysis(latest);
      })
      .catch(() => {
        // Un échec de relecture ne doit pas empêcher de lancer une analyse :
        // le bouton reste disponible.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  function compute() {
    setError(null);
    startTransition(async () => {
      try {
        setAnalysis(await createAnalysis(opportunityId));
      } catch (err) {
        // Une cote manquante ou une trésorerie nulle ne sont pas des pannes :
        // ce sont des dossiers qu'il reste à compléter.
        setError(
          err instanceof ApiError ? err.message : "L'analyse a échoué.",
        );
      }
    });
  }

  const explanation = (analysis?.explanation ?? {}) as Record<string, unknown>;
  const maxPurchase = (explanation.max_purchase ?? {}) as Record<string, string>;
  const saleDelay = (explanation.sale_delay ?? {}) as Record<string, unknown>;
  const record = (explanation.record ?? {}) as {
    score?: string;
    missing?: string[];
  };
  const pillars = (analysis?.pillars ?? {}) as Record<string, unknown>;
  const subscores = (pillars.subscores ?? {}) as Record<string, string>;
  const scenarios = (analysis?.scenario_results ?? {}) as Record<
    string,
    Scenario
  >;
  const portfolio = (analysis?.portfolio_snapshot ?? {}) as Record<
    string,
    string
  >;
  const gates = (analysis?.gates ?? []) as Gate[];
  const caps = analysis?.caps ?? [];
  const verdict = analysis?.recommendation ?? "";

  return (
    <div className="space-y-5">
      {analysis ? (
        <>
          <div
            className={`flex flex-wrap items-center justify-between gap-3 rounded-md border p-4 ${
              VERDICT_TONE[verdict] ?? "border-border"
            }`}
          >
            <div>
              <p className="text-xs uppercase tracking-wide opacity-70">
                Recommandation
              </p>
              <p className="mt-0.5 text-xl font-semibold">
                {labels.recommendation(verdict)}
              </p>
            </div>
            {analysis.score && (
              <div className="text-right">
                <p className="text-xs uppercase tracking-wide opacity-70">
                  Score
                </p>
                <p className="numeric mt-0.5 text-xl font-semibold">
                  {Number(analysis.score).toFixed(1).replace(".", ",")}
                  <span className="text-sm font-normal opacity-60">/100</span>
                </p>
              </div>
            )}
          </div>

          {caps.length > 0 && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
              <p className="mb-1.5 text-xs font-medium text-amber-500">
                Score plafonné
              </p>
              <ul className="space-y-1 text-xs text-fg-muted">
                {caps.map((cap) => {
                  const item = cap as Record<string, string>;
                  return (
                    <li key={item.name}>
                      {labels.cap(item.name)} — plafond{" "}
                      <span className="numeric">{item.value}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-2 text-xs text-fg-muted">
                Score avant plafonnement :{" "}
                <span className="numeric">
                  {String(explanation.raw_score ?? "—")}
                </span>
              </p>
            </div>
          )}

          {/* Prix : ce que l'on peut payer, et ce que l'on vise. */}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-fg-muted">Prix demandé</p>
              <p className="numeric mt-1 text-sm font-medium">
                {formatAmount(analysis.current_price_eur, "EUR")}
              </p>
            </div>
            <div className="rounded-md border border-accent/40 bg-accent/5 p-3">
              <p className="text-xs text-fg-muted">Prix maximal</p>
              <p className="numeric mt-1 text-lg font-semibold text-accent-strong">
                {formatAmount(analysis.max_purchase_price_eur, "EUR")}
              </p>
              <p className="mt-1 text-xs text-fg-muted">
                Contrainte :{" "}
                {labels.bindingConstraint(maxPurchase.binding_constraint)}
              </p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-fg-muted">Prix de revente visé</p>
              <p className="numeric mt-1 text-sm font-medium">
                {formatAmount(analysis.expected_sale_price_eur, "EUR")}
              </p>
              <p className="mt-1 text-xs text-fg-muted">
                sous {String(saleDelay.days ?? "—")} jours
                {saleDelay.thin_evidence ? " (estimation fragile)" : ""}
              </p>
            </div>
          </div>

          {/* Portes : toutes affichées, y compris celles qui passent. Ne
              montrer que les échecs priverait l'utilisateur de la preuve que
              le reste a bien été vérifié. */}
          <section>
            <h3 className="mb-2 text-sm font-medium">Portes d&apos;éligibilité</h3>
            <ul className="divide-y divide-border rounded-md border border-border">
              {gates.map((gate) => (
                <li
                  key={gate.code}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 p-2.5 text-sm"
                >
                  <span>{labels.gate(gate.code)}</span>
                  <span
                    className={`text-xs ${GATE_TONE[gate.status] ?? "text-fg-muted"}`}
                  >
                    {labels.gateStatus(gate.status)}
                  </span>
                  {gate.reason_codes.length > 0 && (
                    <ul className="w-full text-xs text-fg-muted">
                      {gate.reason_codes.map((reason) => (
                        <li key={reason}>— {labels.gateReason(reason)}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {analysis.pillars && (
            <section>
              <h3 className="mb-1 text-sm font-medium">Piliers</h3>
              <div className="divide-y divide-border">
                {Object.keys(PILLAR_WEIGHTS).map((name) =>
                  pillars[name] === undefined ? null : (
                    <Pillar
                      key={name}
                      name={name}
                      value={String(pillars[name])}
                      subscores={subscores}
                    />
                  ),
                )}
              </div>
            </section>
          )}

          {analysis.scenario_results && (
            <section>
              <h3 className="mb-2 text-sm font-medium">Scénarios</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-fg-muted">
                      <th className="pb-1.5 pr-4 font-normal">Scénario</th>
                      <th className="pb-1.5 pr-4 font-normal">Revente</th>
                      <th className="pb-1.5 pr-4 font-normal">Coût total</th>
                      <th className="pb-1.5 pr-4 font-normal">Profit net</th>
                      <th className="pb-1.5 font-normal">ROI</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {["prudent", "central", "favorable"].map((name) => {
                      const row = scenarios[name];
                      if (!row) return null;
                      return (
                        <tr key={name}>
                          <td className="py-1.5 pr-4">
                            {labels.scenario(name)}
                          </td>
                          <td className="numeric py-1.5 pr-4">
                            {formatAmount(row.sale_price_eur, "EUR")}
                          </td>
                          <td className="numeric py-1.5 pr-4">
                            {formatAmount(
                              row.total_cost_before_sale_eur,
                              "EUR",
                            )}
                          </td>
                          <td className="numeric py-1.5 pr-4">
                            {formatAmount(row.net_profit_eur, "EUR")}
                          </td>
                          <td className="numeric py-1.5">
                            {percent(row.roi ?? undefined)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <details>
            <summary className="cursor-pointer text-xs text-fg-muted hover:text-fg">
              Détail du calcul
            </summary>
            <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
              <div className="contents">
                <dt className="text-fg-muted">Trésorerie disponible</dt>
                <dd className="numeric">
                  {formatAmount(portfolio.available_cash_eur, "EUR")}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Stock au coût</dt>
                <dd className="numeric">
                  {formatAmount(portfolio.stock_at_cost_eur, "EUR")}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Allocation après achat</dt>
                <dd className="numeric">
                  {percent(portfolio.allocation_rate)}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Concentration marque</dt>
                <dd className="numeric">
                  {percent(portfolio.brand_concentration_rate)}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Capital immobilisé</dt>
                <dd className="numeric">
                  {percent(portfolio.capital_immobilization_rate)}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Prix maximal avant arrondi</dt>
                <dd className="numeric">
                  {formatAmount(maxPurchase.raw_value_eur, "EUR")} (pas de{" "}
                  {formatAmount(maxPurchase.increment_eur, "EUR")},{" "}
                  {maxPurchase.solver === "closed_form"
                    ? "forme fermée"
                    : "recherche binaire"}
                  )
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Qualité de la fiche</dt>
                <dd className="numeric">
                  {record.score ?? "—"}
                  {record.missing && record.missing.length > 0 && (
                    <span className="text-fg-muted">
                      {" "}
                      — manque :{" "}
                      {record.missing
                        .map((field) => labels.recordField(field))
                        .join(", ")}
                    </span>
                  )}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Barème</dt>
                <dd className="numeric">
                  version {String(explanation.ruleset_version ?? "—")}
                </dd>
              </div>
            </dl>
          </details>

          <p className="text-xs text-fg-muted">
            Calculée le {formatDateTime(analysis.calculated_at)}. Un recalcul
            crée une nouvelle version sans effacer celle-ci.
          </p>
        </>
      ) : (
        loaded && (
          <p className="text-sm text-fg-muted">
            Aucune analyse. Calculez d&apos;abord la cote de marché, puis lancez
            l&apos;analyse.
          </p>
        )
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      <button
        type="button"
        onClick={compute}
        disabled={isPending}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending
          ? "Analyse…"
          : analysis
            ? "Relancer l'analyse"
            : "Lancer l'analyse"}
      </button>
    </div>
  );
}
