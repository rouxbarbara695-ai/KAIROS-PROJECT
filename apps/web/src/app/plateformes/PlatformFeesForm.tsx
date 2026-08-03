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

/** Lit un barème saisi une tranche par ligne, `plafond: taux`.
 *
 *  La dernière ligne s'écrit sans plafond — `au-delà: 0.02` — parce qu'un
 *  barème dont la dernière tranche est bornée ne saurait pas calculer les
 *  montants au-delà, et que l'API le refuse pour cette raison. */
function parseTiers(value: string): { up_to: string | null; rate: string }[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(":").map((part) => part.trim());
      const ceiling = parts[0] ?? "";
      const rate = parts[1] ?? "";
      const open = ceiling === "" || /^(au-delà|au dela|\*|-)$/i.test(ceiling);
      return { up_to: open ? null : ceiling, rate };
    });
}

function formatTiers(
  tiers: { up_to?: string | null; rate: string }[] | undefined,
): string {
  return (tiers ?? [])
    .map((tier) => `${tier.up_to ?? "au-delà"}: ${tier.rate}`)
    .join("\n");
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
    buyerFeeVatRate?: string | null;
    sellerFeeVatRate?: string | null;
    paymentFeeRate?: string | null;
    sellerFeeBasis?: string | null;
    sellerFeeTiers?: { up_to?: string | null; rate: string }[];
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
          buyer_fee_vat_rate: optional(
            String(data.get("buyer_fee_vat_rate") ?? ""),
          ),
          seller_fee_vat_rate: optional(
            String(data.get("seller_fee_vat_rate") ?? ""),
          ),
          payment_fee_rate: optional(String(data.get("payment_fee_rate") ?? "")),
          seller_fee_basis:
            data.get("seller_fee_basis") === "price_and_shipping"
              ? "price_and_shipping"
              : "price",
          seller_fee_tiers: parseTiers(String(data.get("seller_fee_tiers") ?? "")),
          // Le côté acheteur n'a pas encore d'éditeur de barème : aucune
          // plateforme relevée n'en applique un à l'achat. Les valeurs par
          // défaut sont donc explicites plutôt que sous-entendues.
          buyer_fee_basis: "price",
          buyer_fee_tiers: [],
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

      <fieldset className="rounded-md border border-border p-3">
        <legend className="px-1 text-xs text-fg-muted">
          Ce qui s&apos;ajoute à la commission
        </legend>
        <p className="mb-3 text-xs text-fg-muted">
          Laisser vide si la plateforme ne le précise pas : un champ vide
          signale l&apos;inconnu, un zéro affirme qu&apos;il n&apos;y a rien. La
          TVA sur commission n&apos;est un coût que si vous ne la récupérez pas
          — c&apos;est le cas d&apos;un vendeur particulier.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              TVA sur commission achat (ex. 0.20)
            </span>
            <input
              name="buyer_fee_vat_rate"
              inputMode="decimal"
              defaultValue={current?.buyerFeeVatRate ?? ""}
              className={`numeric ${inputClass}`}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              TVA sur commission vente (ex. 0.20)
            </span>
            <input
              name="seller_fee_vat_rate"
              inputMode="decimal"
              defaultValue={current?.sellerFeeVatRate ?? ""}
              className={`numeric ${inputClass}`}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              Frais de paiement vendeur (ex. 0.03)
            </span>
            <input
              name="payment_fee_rate"
              inputMode="decimal"
              defaultValue={current?.paymentFeeRate ?? ""}
              className={`numeric ${inputClass}`}
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="rounded-md border border-border p-3">
        <legend className="px-1 text-xs text-fg-muted">
          Barème par tranches et base de calcul
        </legend>
        <p className="mb-3 text-xs text-fg-muted">
          eBay prélève 10 % sur les 2 000 premiers euros puis 2 % au-delà, sur
          un montant qui inclut le port. Un taux unique se tromperait du simple
          au double selon le prix : saisir le barème plutôt qu&apos;une
          moyenne.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              Tranches de commission vente (une par ligne)
            </span>
            <textarea
              name="seller_fee_tiers"
              rows={3}
              defaultValue={formatTiers(current?.sellerFeeTiers)}
              placeholder={"2000: 0.10\nau-delà: 0.02"}
              className={`numeric ${inputClass}`}
            />
            <span className="mt-1 block text-xs text-fg-muted">
              Format « plafond : taux ». La dernière ligne s&apos;écrit
              « au-delà », sans quoi les montants supérieurs ne pourraient pas
              se calculer. Un barème renseigné remplace le taux unique.
            </span>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              Base de la commission vente
            </span>
            <select
              name="seller_fee_basis"
              defaultValue={current?.sellerFeeBasis ?? "price"}
              className={inputClass}
            >
              <option value="price">Prix de la montre seul</option>
              <option value="price_and_shipping">
                Prix + frais de port (eBay)
              </option>
            </select>
          </label>
        </div>
      </fieldset>

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
