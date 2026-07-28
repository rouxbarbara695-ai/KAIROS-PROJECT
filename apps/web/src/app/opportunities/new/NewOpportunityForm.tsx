"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/Card";
import { ApiError, createOpportunity } from "@/lib/api";

const MECHANICAL_OPTIONS = ["verified", "functional", "unknown", "defect"];
const COSMETIC_OPTIONS = ["excellent", "very_good", "good", "fair", "poor"];
const SELLER_TYPES = ["private", "professional", "unknown"];

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-fg-muted">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

export function NewOpportunityForm({ portfolioId }: { portfolioId?: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!portfolioId) {
      setError("Aucun portefeuille disponible.");
      return;
    }

    const data = new FormData(event.currentTarget);
    const box = data.get("box") === "on";
    const papers = data.get("papers") === "on";
    const amount = String(data.get("amount") ?? "").trim();

    startTransition(async () => {
      try {
        const opportunity = await createOpportunity({
          portfolio_id: portfolioId,
          source: {
            mode: "manual",
            manual_identifier: String(data.get("manual_identifier")),
          },
          watch: {
            brand: String(data.get("brand")),
            reference: String(data.get("reference")),
            reference_status: "unconfirmed",
            mechanical_condition: String(data.get("mechanical_condition")),
            cosmetic_condition: String(data.get("cosmetic_condition")),
            box,
            papers,
          },
          seller: {
            country_code: String(data.get("country_code") || "") || undefined,
            seller_type: String(data.get("seller_type") || "") || undefined,
          },
          price: amount
            ? { amount, currency: String(data.get("currency")) }
            : {},
        });
        router.push(`/opportunities/${opportunity.id}`);
      } catch (err) {
        if (err instanceof ApiError && err.code === "OPPORTUNITY_DUPLICATE") {
          setError(
            "Cette opportunité existe déjà (identifiant ou URL en double).",
          );
        } else {
          setError("La création a échoué. Vérifiez les champs.");
        }
      }
    });
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-5">
        <Field label="Identifiant manuel">
          <input
            name="manual_identifier"
            required
            className={inputClass}
            placeholder="LONGINES-2026-001"
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Marque">
            <input name="brand" required className={inputClass} />
          </Field>
          <Field label="Référence">
            <input name="reference" required className={inputClass} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="État mécanique">
            <select name="mechanical_condition" className={inputClass}>
              {MECHANICAL_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>
          <Field label="État cosmétique">
            <select name="cosmetic_condition" className={inputClass}>
              {COSMETIC_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="box" className="accent-accent" />
            Boîte
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="papers"
              className="accent-accent"
            />
            Papiers
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Pays du vendeur">
            <input
              name="country_code"
              maxLength={2}
              placeholder="FR"
              className={inputClass}
            />
          </Field>
          <Field label="Type de vendeur">
            <select name="seller_type" className={inputClass} defaultValue="">
              <option value="">—</option>
              {SELLER_TYPES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Prix (optionnel)">
            <input
              name="amount"
              inputMode="decimal"
              placeholder="1800.00"
              className={inputClass}
            />
          </Field>
          <Field label="Devise">
            <input
              name="currency"
              defaultValue="EUR"
              maxLength={3}
              className={inputClass}
            />
          </Field>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <button
          type="submit"
          disabled={isPending}
          className="w-full rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-bg disabled:opacity-50"
        >
          {isPending ? "Création…" : "Créer l'opportunité"}
        </button>
      </form>
    </Card>
  );
}
