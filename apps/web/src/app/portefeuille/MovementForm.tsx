"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError, createLedgerEntry } from "@/lib/api";

/**
 * Natures saisissables.
 *
 * Les paiements d'achat et encaissements de vente n'y figurent pas : ils ont
 * leur ligne dans les opérations, et les saisir ici ferait diverger le
 * registre de ce qu'il reflète. L'API les refuse d'ailleurs.
 */
const KINDS = [
  { value: "capital_contribution", label: "Apport de capital" },
  { value: "withdrawal", label: "Retrait" },
  { value: "positive_adjustment", label: "Ajustement positif" },
  { value: "negative_adjustment", label: "Ajustement négatif" },
] as const;

export function MovementForm({ portfolioId }: { portfolioId: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [kind, setKind] = useState<string>("capital_contribution");
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        await createLedgerEntry(portfolioId, {
          kind: kind as "capital_contribution",
          // Le montant part en chaîne décimale : le passer en nombre JSON
          // perdrait des centimes que l'API refuse justement de deviner.
          amount,
          currency: "EUR",
          notes: notes.trim() || null,
        });
        setAmount("");
        setNotes("");
        router.refresh();
      } catch (err) {
        // Un retrait au-delà de la trésorerie n'est pas une panne : c'est le
        // registre qui refuse de constater un découvert qui n'a pas eu lieu.
        setError(
          err instanceof ApiError
            ? err.message
            : "L'enregistrement du mouvement a échoué.",
        );
      }
    });
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">Nature</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent"
          >
            {KINDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">Montant (€)</span>
          <input
            type="text"
            inputMode="decimal"
            required
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="2000.00"
            className="numeric w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent sm:w-40"
          />
        </label>
      </div>

      <label className="block">
        <span className="mb-1 block text-xs text-fg-muted">
          Note (facultatif)
        </span>
        <input
          type="text"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Virement depuis le compte courant"
          className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent"
        />
      </label>

      {error && <p className="text-sm text-danger">{error}</p>}

      <button
        type="submit"
        disabled={isPending || !amount.trim()}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending ? "Enregistrement…" : "Enregistrer le mouvement"}
      </button>

      <p className="text-xs text-fg-muted">
        Le registre ne se corrige pas : pour annuler une écriture, on en passe
        une autre en sens inverse. C&apos;est ce qui permet à la trésorerie de
        s&apos;expliquer ligne à ligne.
      </p>
    </form>
  );
}
