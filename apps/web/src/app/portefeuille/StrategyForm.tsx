"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError, updateStrategy } from "@/lib/api";

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent";

const NONE = "__none__";

/** Un champ vide veut dire « n'y touche pas » : la version courante est
 *  reprise pour tout ce qu'on ne mentionne pas. */
function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function StrategyForm({
  portfolioId,
  platforms,
  current,
}: {
  portfolioId: string;
  platforms: { code: string; name: string; hasRule: boolean }[];
  current: {
    minimumRoi: string;
    minimumProfitEur: string;
    maximumAllocationRate: string;
    negotiationBuffer: string;
    resalePlatformCode: string | null;
  };
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    const resale = String(data.get("resale_platform_code"));

    startTransition(async () => {
      try {
        await updateStrategy(portfolioId, {
          minimum_roi: optional(String(data.get("minimum_roi") ?? "")),
          minimum_profit_eur: optional(
            String(data.get("minimum_profit_eur") ?? ""),
          ),
          maximum_allocation_rate: optional(
            String(data.get("maximum_allocation_rate") ?? ""),
          ),
          negotiation_buffer: optional(
            String(data.get("negotiation_buffer") ?? ""),
          ),
          // Retirer une plateforme se dit explicitement : un champ vide se
          // confondrait avec « n'y touche pas ».
          clear_resale_platform: resale === NONE,
          resale_platform_code: resale === NONE ? null : resale,
        });
        router.refresh();
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "L'enregistrement de la stratégie a échoué.",
        );
      }
    });
  }

  const selected = current.resalePlatformCode ?? NONE;
  const chosen = platforms.find(
    (platform) => platform.code === current.resalePlatformCode,
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <label className="block">
        <span className="mb-1 block text-xs text-fg-muted">
          Plateforme de revente
        </span>
        <select
          name="resale_platform_code"
          defaultValue={selected}
          className={inputClass}
        >
          <option value={NONE}>
            Aucune — revente de particulier à particulier
          </option>
          {platforms.map((platform) => (
            <option key={platform.code} value={platform.code}>
              {platform.name}
              {platform.hasRule ? "" : " (grille de frais manquante)"}
            </option>
          ))}
        </select>
      </label>

      {chosen && !chosen.hasRule && (
        <p className="text-xs text-amber-500">
          {chosen.name} n&apos;a pas de grille de frais : l&apos;analyse
          refusera de s&apos;exécuter tant qu&apos;elle n&apos;est pas saisie,
          plutôt que de supposer une revente gratuite.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            ROI minimal (ex. 0.20)
          </span>
          <input
            name="minimum_roi"
            inputMode="decimal"
            defaultValue={current.minimumRoi}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Profit minimal (€)
          </span>
          <input
            name="minimum_profit_eur"
            inputMode="decimal"
            defaultValue={current.minimumProfitEur}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Allocation maximale (ex. 0.50)
          </span>
          <input
            name="maximum_allocation_rate"
            inputMode="decimal"
            defaultValue={current.maximumAllocationRate}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Tampon de négociation (ex. 0.08)
          </span>
          <input
            name="negotiation_buffer"
            inputMode="decimal"
            defaultValue={current.negotiationBuffer}
            className={`numeric ${inputClass}`}
          />
        </label>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <button
        type="submit"
        disabled={isPending}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending ? "Enregistrement…" : "Enregistrer une nouvelle version"}
      </button>

      <p className="text-xs text-fg-muted">
        Une version de stratégie n&apos;est jamais réécrite : les analyses déjà
        publiées référencent celle qui les a produites et restent explicables.
      </p>
    </form>
  );
}
