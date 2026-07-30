"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError, createPlatformRule } from "@/lib/api";

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent";

/** Un champ vide reste vide : `null`, pas `0`. Une commission absente et une
 *  commission nulle ne disent pas la même chose. */
function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function PlatformFeesForm({
  code,
  name,
  current,
}: {
  code: string;
  name: string;
  current: {
    buyerFeeRate?: string | null;
    buyerFeeFixed?: string | null;
    sellerFeeRate?: string | null;
    sellerFeeFixed?: string | null;
    sellerFeeMin?: string | null;
    sellerFeeMax?: string | null;
    provenanceUrl?: string | null;
  } | null;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    startTransition(async () => {
      try {
        await createPlatformRule(code, {
          region_code: "*",
          currency: "EUR",
          provenance_url: String(data.get("provenance_url")),
          buyer_fee_rate: optional(String(data.get("buyer_fee_rate") ?? "")),
          buyer_fee_fixed: optional(String(data.get("buyer_fee_fixed") ?? "")),
          seller_fee_rate: optional(String(data.get("seller_fee_rate") ?? "")),
          seller_fee_fixed: optional(String(data.get("seller_fee_fixed") ?? "")),
          seller_fee_min: optional(String(data.get("seller_fee_min") ?? "")),
          seller_fee_max: optional(String(data.get("seller_fee_max") ?? "")),
        });
        router.refresh();
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "L'enregistrement de la grille a échoué.",
        );
      }
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Commission achat (taux, ex. 0.09)
          </span>
          <input
            name="buyer_fee_rate"
            inputMode="decimal"
            defaultValue={current?.buyerFeeRate ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Frais fixes achat (€)
          </span>
          <input
            name="buyer_fee_fixed"
            inputMode="decimal"
            defaultValue={current?.buyerFeeFixed ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Commission vente (taux, ex. 0.125)
          </span>
          <input
            name="seller_fee_rate"
            inputMode="decimal"
            defaultValue={current?.sellerFeeRate ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Frais fixes vente (€)
          </span>
          <input
            name="seller_fee_fixed"
            inputMode="decimal"
            defaultValue={current?.sellerFeeFixed ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Commission vente minimale (€)
          </span>
          <input
            name="seller_fee_min"
            inputMode="decimal"
            defaultValue={current?.sellerFeeMin ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">
            Commission vente plafonnée (€)
          </span>
          <input
            name="seller_fee_max"
            inputMode="decimal"
            defaultValue={current?.sellerFeeMax ?? ""}
            className={`numeric ${inputClass}`}
          />
        </label>
      </div>

      <label className="block">
        <span className="mb-1 block text-xs text-fg-muted">
          Source de la grille (obligatoire)
        </span>
        <input
          name="provenance_url"
          required
          defaultValue={current?.provenanceUrl ?? ""}
          placeholder="https://…/frais-de-vente"
          className={inputClass}
        />
      </label>

      {error && <p className="text-sm text-danger">{error}</p>}

      <button
        type="submit"
        disabled={isPending}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending
          ? "Enregistrement…"
          : current
            ? `Nouvelle version pour ${name}`
            : `Enregistrer la grille de ${name}`}
      </button>
    </form>
  );
}
