"use client";

import { useState, useTransition, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  addPriceInput,
  ApiError,
  patchSellerProfile,
  patchWatchProfile,
} from "@/lib/api";
import { labels, options, PRICE_KIND_OPTIONS } from "@/lib/labels";

const inputClass =
  "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-fg-muted">{label}</span>
      {children}
    </label>
  );
}

/**
 * Toute correction exige un motif (contrat API, § Correction). Le bouton reste
 * inactif tant qu'il est vide : la contrainte est rappelée à la saisie plutôt
 * que subie sous forme d'erreur serveur.
 */
function useCorrection(onDone: () => void) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function submit(action: () => Promise<unknown>) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
        onDone();
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "La correction a échoué. Vérifiez les champs.",
        );
      }
    });
  }

  return { isPending, error, submit };
}

function SubmitRow({
  isPending,
  error,
  label,
}: {
  isPending: boolean;
  error: string | null;
  label: string;
}) {
  return (
    <>
      {error && <p className="text-sm text-danger">{error}</p>}
      <button
        type="submit"
        disabled={isPending}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
      >
        {isPending ? "Enregistrement…" : label}
      </button>
    </>
  );
}

export function WatchProfileForm({
  opportunityId,
  current,
}: {
  opportunityId: string;
  current: { mechanical?: string; cosmetic?: string; completeness?: string };
}) {
  const router = useRouter();
  const { isPending, error, submit } = useCorrection(() => router.refresh());
  const [editSet, setEditSet] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const form = event.currentTarget;
    submit(async () => {
      // `box` et `papers` ne sont transmis que si le set est explicitement
      // modifié : l'API interprète leur absence comme « ne pas toucher », et
      // des cases décochées par défaut effaceraient sinon un set existant.
      await patchWatchProfile(opportunityId, {
        mechanical_condition: String(data.get("mechanical_condition")),
        cosmetic_condition: String(data.get("cosmetic_condition")),
        ...(editSet
          ? {
              box: data.get("box") === "on",
              papers: data.get("papers") === "on",
            }
          : {}),
        reason: String(data.get("reason")),
      });
      form.reset();
      setEditSet(false);
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="État mécanique">
          <select
            name="mechanical_condition"
            className={inputClass}
            defaultValue={current.mechanical}
          >
            {options.mechanicalCondition.map((option) => (
              <option key={option} value={option}>
                {labels.mechanicalCondition(option)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="État cosmétique">
          <select
            name="cosmetic_condition"
            className={inputClass}
            defaultValue={current.cosmetic}
          >
            {options.cosmeticCondition.map((option) => (
              <option key={option} value={option}>
                {labels.cosmeticCondition(option)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={editSet}
            onChange={(event) => setEditSet(event.target.checked)}
            className="accent-accent"
          />
          Modifier aussi le set
          <span className="text-xs text-fg-muted">
            (actuellement : {labels.completenessLevel(current.completeness)})
          </span>
        </label>
        {editSet && (
          <div className="flex gap-6 pl-6">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" name="box" className="accent-accent" />
              Boîte
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" name="papers" className="accent-accent" />
              Papiers
            </label>
          </div>
        )}
      </div>
      <Field label="Motif (obligatoire)">
        <input
          name="reason"
          required
          className={inputClass}
          placeholder="ex. rayures constatées sur le fond"
        />
      </Field>
      <SubmitRow isPending={isPending} error={error} label="Corriger l'état" />
    </form>
  );
}

export function SellerProfileForm({
  opportunityId,
  current,
}: {
  opportunityId: string;
  current: { countryCode?: string | null; sellerType?: string | null };
}) {
  const router = useRouter();
  const { isPending, error, submit } = useCorrection(() => router.refresh());

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const form = event.currentTarget;
    const countryCode = String(data.get("country_code") ?? "").trim();
    submit(async () => {
      await patchSellerProfile(opportunityId, {
        ...(countryCode ? { country_code: countryCode } : {}),
        seller_type: String(data.get("seller_type")),
        reason: String(data.get("reason")),
      });
      form.reset();
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Pays">
          <input
            name="country_code"
            maxLength={2}
            defaultValue={current.countryCode ?? ""}
            className={inputClass}
            placeholder="FR"
          />
        </Field>
        <Field label="Type de vendeur">
          <select
            name="seller_type"
            className={inputClass}
            defaultValue={current.sellerType ?? "unknown"}
          >
            {options.sellerType.map((option) => (
              <option key={option} value={option}>
                {labels.sellerType(option)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Motif (obligatoire)">
        <input
          name="reason"
          required
          className={inputClass}
          placeholder="ex. boutique identifiée sur l'annonce"
        />
      </Field>
      <SubmitRow
        isPending={isPending}
        error={error}
        label="Corriger le vendeur"
      />
    </form>
  );
}

export function PriceInputForm({ opportunityId }: { opportunityId: string }) {
  const router = useRouter();
  const { isPending, error, submit } = useCorrection(() => router.refresh());
  const [hasAmount, setHasAmount] = useState(true);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const form = event.currentTarget;
    const amount = String(data.get("amount") ?? "").trim();
    const missingReason = String(data.get("missing_reason") ?? "").trim();

    submit(async () => {
      await addPriceInput(opportunityId, {
        kind: String(data.get("kind")) as "asking",
        ...(amount
          ? { amount, currency: String(data.get("currency")) }
          : { missing_reason: missingReason }),
      });
      form.reset();
      setHasAmount(true);
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Field label="Type de prix">
        <select name="kind" className={inputClass}>
          {PRICE_KIND_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {labels.priceKind(option)}
            </option>
          ))}
        </select>
      </Field>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={!hasAmount}
          onChange={(event) => setHasAmount(!event.target.checked)}
          className="accent-accent"
        />
        Prix non communiqué
      </label>

      {hasAmount ? (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Montant">
            <input
              name="amount"
              required
              inputMode="decimal"
              className={inputClass}
              placeholder="1800.00"
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
      ) : (
        <Field label="Motif de l'absence de prix">
          <input
            name="missing_reason"
            required
            className={inputClass}
            placeholder="ex. prix sur demande"
          />
        </Field>
      )}

      <SubmitRow
        isPending={isPending}
        error={error}
        label="Ajouter le relevé"
      />
    </form>
  );
}
