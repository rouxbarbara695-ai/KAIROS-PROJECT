"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ApiError,
  changeStatus,
  recordPayout,
  recordPurchase,
  recordSale,
  recordSaleListing,
} from "@/lib/api";

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent";

const buttonClass =
  "rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50";

/** Les gestes qui ne portent aucune donnée propre. Ceux qui constatent une
 *  opération — achat, mise en vente, vente, encaissement — ont leur formulaire :
 *  ils écrivent une ligne d'opération que le statut seul ne produirait pas. */
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
  listed_for_sale: [
    { target: "awaiting_buyer_payment", label: "Un acheteur s'est engagé" },
    { target: "in_stock", label: "Retirer de la vente" },
  ],
  awaiting_buyer_payment: [
    { target: "listed_for_sale", label: "L'acheteur s'est désisté" },
  ],
  awaiting_payout: [
    { target: "listed_for_sale", label: "La vente a échoué, remettre en vente" },
  ],
  abandoned: [{ target: "watching", label: "Rouvrir" }],
};

function Field({
  name,
  label,
  hint,
  placeholder,
  required = true,
  numeric = false,
}: {
  name: string;
  label: string;
  hint?: string;
  placeholder?: string;
  required?: boolean;
  numeric?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-fg-muted">{label}</span>
      <input
        name={name}
        required={required}
        inputMode={numeric ? "decimal" : undefined}
        placeholder={placeholder}
        className={`${numeric ? "numeric " : ""}${inputClass}`}
      />
      {hint && <span className="mt-1 block text-xs text-fg-muted">{hint}</span>}
    </label>
  );
}

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

  function submit(
    event: React.FormEvent<HTMLFormElement>,
    handler: (data: FormData) => Promise<unknown>,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    run(() => handler(data));
  }

  const optional = (data: FormData, key: string): string | undefined => {
    const value = String(data.get(key) ?? "").trim();
    return value === "" ? undefined : value;
  };

  return (
    <div className="space-y-4">
      {(status === "buy" || status === "auction") && (
        <form
          onSubmit={(event) =>
            submit(event, (data) =>
              recordPurchase(opportunityId, {
                amount: String(data.get("amount")),
                currency: "EUR",
                reason: String(data.get("reason")),
              }),
            )
          }
          className="space-y-3"
        >
          {/* Volontairement vide : préremplir avec le prix demandé ou le
              maximum calculé ferait ressaisir une valeur que KAIROS a
              lui-même produite, et le coût de revient serait faux dès la
              première négociation réussie. */}
          <Field
            name="amount"
            numeric
            label="Prix réellement payé (€)"
            placeholder="ce que tu as payé, pas le prix affiché"
            hint={askingPrice ? `Prix demandé : ${askingPrice}` : undefined}
          />
          <Field
            name="reason"
            label="Motif"
            placeholder="Négocié sur place, lot d'enchère…"
          />
          <button type="submit" disabled={isPending} className={buttonClass}>
            {isPending ? "Enregistrement…" : "Enregistrer l'achat"}
          </button>
          <p className="text-xs text-fg-muted">
            L&apos;achat sort la trésorerie et fait entrer la montre au stock.
          </p>
        </form>
      )}

      {status === "in_stock" && (
        <form
          onSubmit={(event) =>
            submit(event, (data) =>
              recordSaleListing(opportunityId, {
                asking_amount: String(data.get("asking_amount")),
                currency: "EUR",
                platform_code: optional(data, "platform_code") ?? null,
                external_url: optional(data, "external_url") ?? null,
                reason: String(data.get("reason")),
              }),
            )
          }
          className="space-y-3"
        >
          <Field
            name="asking_amount"
            numeric
            label="Prix demandé (€)"
            placeholder="ce que tu affiches"
          />
          <Field
            name="platform_code"
            label="Plateforme"
            required={false}
            placeholder="chrono24, ebay… vide pour une vente directe"
          />
          <Field
            name="external_url"
            label="Lien de l'annonce"
            required={false}
            placeholder="facultatif"
          />
          <Field name="reason" label="Motif" placeholder="Stratégie de prix…" />
          <button type="submit" disabled={isPending} className={buttonClass}>
            {isPending ? "Enregistrement…" : "Mettre en vente"}
          </button>
        </form>
      )}

      {status === "awaiting_buyer_payment" && (
        <form
          onSubmit={(event) =>
            submit(event, (data) =>
              recordSale(opportunityId, {
                realized_amount: String(data.get("realized_amount")),
                currency: "EUR",
                reason: String(data.get("reason")),
              }),
            )
          }
          className="space-y-3"
        >
          <Field
            name="realized_amount"
            numeric
            label="Prix réalisé (€)"
            placeholder="ce sur quoi vous vous êtes entendus"
          />
          <Field name="reason" label="Motif" placeholder="Vendue à…" />
          <button type="submit" disabled={isPending} className={buttonClass}>
            {isPending ? "Enregistrement…" : "Enregistrer la vente"}
          </button>
          <p className="text-xs text-fg-muted">
            La trésorerie ne bouge pas encore : les fonds sont retenus jusqu&apos;à
            l&apos;encaissement.
          </p>
        </form>
      )}

      {status === "awaiting_payout" && (
        <form
          onSubmit={(event) =>
            submit(event, (data) =>
              recordPayout(opportunityId, {
                amount: optional(data, "amount") ?? null,
                currency: "EUR",
                reason: String(data.get("reason")),
              }),
            )
          }
          className="space-y-3"
        >
          <Field
            name="amount"
            numeric
            required={false}
            label="Montant reçu (€)"
            placeholder="laisser vide si le prix réalisé a été versé tel quel"
            hint="Commission de plateforme déjà déduite : saisir ce qui est arrivé sur le compte."
          />
          <Field name="reason" label="Motif" placeholder="Virement reçu le…" />
          <button type="submit" disabled={isPending} className={buttonClass}>
            {isPending ? "Enregistrement…" : "Constater l'encaissement"}
          </button>
        </form>
      )}

      {status === "sold" && (
        <p className="text-sm text-fg-muted">
          Opération terminée. Une vente ne se défait pas : une correction passe
          par une écriture de registre en sens inverse.
        </p>
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
                  `Motif du geste « ${action.label} » :`,
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

      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
