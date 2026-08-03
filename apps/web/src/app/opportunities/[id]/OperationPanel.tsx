"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError, changeStatus, recordPurchase } from "@/lib/api";

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent";

const buttonClass =
  "rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50";

/** Le libellé de chaque geste possible, dans l'ordre du cycle. `purchased` et
 *  `sold` n'y figurent pas : ils constatent une opération et s'obtiennent en
 *  l'enregistrant, pas en changeant le statut. */
const STATUS_ACTIONS: Record<string, { target: string; label: string }[]> = {
  watching: [
    { target: "buy", label: "Décider d'acheter" },
    { target: "auction", label: "Suivre l'enchère" },
    { target: "abandoned", label: "Abandonner" },
  ],
  buy: [
    { target: "watching", label: "Revenir en veille" },
    { target: "abandoned", label: "Abandonner" },
  ],
  auction: [
    { target: "watching", label: "Revenir en veille" },
    { target: "abandoned", label: "Abandonner" },
  ],
  purchased: [{ target: "in_stock", label: "Marquer reçue" }],
  in_stock: [{ target: "listed_for_sale", label: "Mettre en vente" }],
  abandoned: [{ target: "watching", label: "Rouvrir" }],
};

export function OperationPanel({
  opportunityId,
  status,
  askingPrice,
}: {
  opportunityId: string;
  status: string;
  askingPrice: string | null;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const canBuy = status === "buy" || status === "auction";
  const actions = STATUS_ACTIONS[status] ?? [];

  function run(action: () => Promise<unknown>) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
        router.refresh();
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "L'opération a échoué.",
        );
      }
    });
  }

  function handlePurchase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    run(() =>
      recordPurchase(opportunityId, {
        amount: String(data.get("amount")),
        currency: "EUR",
        reason: String(data.get("reason")),
      }),
    );
  }

  return (
    <div className="space-y-4">
      {canBuy && (
        <form onSubmit={handlePurchase} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              Prix réellement payé (€)
            </span>
            {/* Volontairement vide : préremplir avec le prix demandé ou le
                maximum calculé ferait ressaisir une valeur que KAIROS a
                lui-même produite, et le coût de revient serait faux dès la
                première négociation réussie. */}
            <input
              name="amount"
              inputMode="decimal"
              required
              placeholder="ce que tu as payé, pas le prix affiché"
              className={`numeric ${inputClass}`}
            />
            {askingPrice && (
              <span className="mt-1 block text-xs text-fg-muted">
                Prix demandé : {askingPrice}
              </span>
            )}
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-fg-muted">
              Motif (obligatoire)
            </span>
            <input
              name="reason"
              required
              placeholder="Négocié sur place, lot d'enchère…"
              className={inputClass}
            />
          </label>
          <button type="submit" disabled={isPending} className={buttonClass}>
            {isPending ? "Enregistrement…" : "Enregistrer l'achat"}
          </button>
          <p className="text-xs text-fg-muted">
            L&apos;achat sort la trésorerie et fait entrer la montre au stock.
            L&apos;écriture de registre en découle : elle ne se saisit pas à la
            main.
          </p>
        </form>
      )}

      {actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => (
            <button
              key={action.target}
              type="button"
              disabled={isPending}
              onClick={() => {
                const reason = window.prompt(
                  `Motif du passage à « ${action.label.toLowerCase()} » :`,
                );
                if (!reason?.trim()) return;
                run(() =>
                  changeStatus(opportunityId, {
                    status: action.target,
                    reason,
                  }),
                );
              }}
              className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {actions.length === 0 && !canBuy && (
        <p className="text-sm text-fg-muted">
          Aucun geste disponible depuis ce statut.
        </p>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
