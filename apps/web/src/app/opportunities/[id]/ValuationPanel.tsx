"use client";

import { useState, useTransition } from "react";
import { ApiError, createValuation, type ValuationResponse } from "@/lib/api";
import { formatAmount, formatDateTime } from "@/lib/labels";

const CAP_LABELS: Record<string, string> = {
  no_ab: "Aucune preuve de classe A ou B",
  two_comparables: "Seulement deux comparables",
  identity_unconfirmed: "Référence non confirmée",
  single_seller: "Un seul vendeur",
};

const COMPONENT_LABELS: Record<string, string> = {
  volume: "Volume",
  source_reliability: "Fiabilité des sources",
  recency: "Récence",
  similarity: "Similarité",
  dispersion: "Dispersion",
};

function ConfidenceBar({ value }: { value: number }) {
  const tone =
    value >= 70 ? "bg-accent" : value >= 40 ? "bg-amber-500" : "bg-danger";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
      <div
        className={`h-full rounded-full ${tone}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function ValuationPanel({ opportunityId }: { opportunityId: string }) {
  const [isPending, startTransition] = useTransition();
  const [valuation, setValuation] = useState<ValuationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function compute() {
    setError(null);
    startTransition(async () => {
      try {
        setValuation(await createValuation(opportunityId));
      } catch (err) {
        // Un nombre insuffisant de comparables n'est pas une panne : c'est
        // l'état normal d'un dossier qu'il reste à documenter.
        setError(
          err instanceof ApiError
            ? err.message
            : "Le calcul de la cote a échoué.",
        );
      }
    });
  }

  const explanation = (valuation?.explanation ?? {}) as Record<string, unknown>;
  const confidence = (explanation.confidence ?? {}) as Record<string, unknown>;
  const caps = (confidence.applied_caps ?? []) as {
    name: string;
    value: string;
    reason: string;
  }[];
  const confidenceValue = valuation
    ? Number(valuation.valuation_confidence)
    : 0;
  const anomalies = Number(explanation.comparables_flagged_as_anomaly ?? 0);

  return (
    <div className="space-y-4">
      {valuation ? (
        <>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-fg-muted">Prudente</p>
              <p className="numeric mt-1 text-sm font-medium">
                {formatAmount(valuation.low_value_eur, "EUR")}
              </p>
            </div>
            <div className="rounded-md border border-accent/40 bg-accent/5 p-3">
              <p className="text-xs text-fg-muted">Centrale</p>
              <p className="numeric mt-1 text-lg font-semibold text-accent-strong">
                {formatAmount(valuation.central_value_eur, "EUR")}
              </p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-fg-muted">Favorable</p>
              <p className="numeric mt-1 text-sm font-medium">
                {formatAmount(valuation.high_value_eur, "EUR")}
              </p>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-fg-muted">Confiance</span>
              <span className="numeric font-medium">
                {confidenceValue.toFixed(0)}/100
              </span>
            </div>
            <ConfidenceBar value={confidenceValue} />
          </div>

          {anomalies > 0 && (
            <div className="rounded-md border border-border bg-surface-hover p-3">
              <p className="text-xs text-fg-muted">
                <span className="font-medium text-fg">
                  {anomalies} comparable(s) écarté(s) automatiquement
                </span>{" "}
                — prix trop éloigné du groupe pour être retenu. Ils restent
                enregistrés et figurent dans la trace ; seule leur contribution
                à cette cote est neutralisée.
              </p>
            </div>
          )}

          {caps.length > 0 && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
              <p className="mb-1.5 text-xs font-medium text-amber-500">
                Confiance plafonnée
              </p>
              <ul className="space-y-1 text-xs text-fg-muted">
                {caps.map((cap) => (
                  <li key={cap.name}>
                    {CAP_LABELS[cap.name] ?? cap.name} — plafond {cap.value}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <details>
            <summary className="cursor-pointer text-xs text-fg-muted hover:text-fg">
              Détail du calcul
            </summary>
            <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
              {Object.entries(COMPONENT_LABELS).map(([key, label]) => (
                <div key={key} className="contents">
                  <dt className="text-fg-muted">{label}</dt>
                  <dd className="numeric">{String(confidence[key] ?? "—")}</dd>
                </div>
              ))}
              <div className="contents">
                <dt className="text-fg-muted">Comparables retenus</dt>
                <dd className="numeric">
                  {String(explanation.comparables_used ?? "—")} sur{" "}
                  {String(explanation.comparables_total ?? "—")}
                </dd>
              </div>
              <div className="contents">
                <dt className="text-fg-muted">Anomalies écartées</dt>
                <dd className="numeric">
                  {String(explanation.comparables_flagged_as_anomaly ?? "—")}
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
            Calculée le {formatDateTime(valuation.calculated_at)}. Un recalcul
            crée une nouvelle version sans effacer celle-ci.
          </p>
        </>
      ) : (
        <p className="text-sm text-fg-muted">
          Aucune cote calculée. Ajoutez au moins deux comparables recevables,
          puis lancez le calcul.
        </p>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      <button
        type="button"
        onClick={compute}
        disabled={isPending}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending
          ? "Calcul…"
          : valuation
            ? "Recalculer la cote"
            : "Calculer la cote"}
      </button>
    </div>
  );
}
