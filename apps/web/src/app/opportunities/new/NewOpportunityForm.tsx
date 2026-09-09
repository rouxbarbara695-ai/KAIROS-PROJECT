"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/Card";
import {
  ApiError,
  createOpportunity,
  type ListingPrefillResponse,
} from "@/lib/api";
import { useActionKeys } from "@/lib/idempotency";
import { ListingPrefill } from "./ListingPrefill";
import { labels, options } from "@/lib/labels";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-fg-muted">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

export function NewOpportunityForm({
  portfolioId,
  platforms = [],
}: {
  portfolioId?: string;
  platforms?: { code: string; name: string; hasRule: boolean }[];
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"manual" | "url">("manual");
  const { keyFor, settle } = useActionKeys();

  const [url, setUrl] = useState("");
  // Valeurs reprises d'une annonce. Elles servent de valeurs par défaut ; ce
  // que l'utilisateur tape ensuite reste dans le DOM et n'est pas piloté ici.
  const [imported, setImported] = useState<Record<string, string | boolean>>(
    {},
  );
  // Compteur de remontage : changer la clé d'un champ non contrôlé est la
  // seule façon de lui redonner une valeur par défaut sans transformer tout
  // le formulaire en état React.
  const [importVersion, setImportVersion] = useState(0);
  const [hasUserEdits, setHasUserEdits] = useState(false);
  // Renvoyé tel quel à la création. Sans lui, le dossier rouvert ne dirait
  // plus quelle valeur venait de l'annonce et laquelle a été corrigée.
  const [draft, setDraft] = useState<ListingPrefillResponse | null>(null);

  /**
   * Une frappe dans le panneau d'import n'est pas une correction de champ.
   *
   * Le panneau vit à l'intérieur du formulaire : sans cette distinction,
   * saisir le lien et coller le contenu marquait le dossier comme « corrigé à
   * la main », et le tout premier import demandait de confirmer un écrasement
   * qui n'existait pas.
   */
  function markUserEdit(event: React.SyntheticEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("[data-import-panel]")) return;
    setHasUserEdits(true);
  }

  function applyPrefill(result: ListingPrefillResponse) {
    const fields = result.fields ?? {};
    const value = (name: string): string | boolean | undefined => {
      const field = fields[name];
      if (!field || field.provenance === "absent") return undefined;
      if (field.value === null || field.value === undefined) return undefined;
      return field.value as string | boolean;
    };

    const next: Record<string, string | boolean> = {};
    for (const name of [
      "brand",
      "reference",
      "box",
      "papers",
      "seller_country",
      "seller_type",
      "price_amount",
      "price_currency",
    ]) {
      const found = value(name);
      // Un champ absent de l'annonce n'écrase rien et ne pose aucun défaut :
      // « non renseigné » doit rester « non renseigné ».
      if (found !== undefined) next[name] = found;
    }

    setImported(next);
    setDraft(result);
    setImportVersion((version) => version + 1);
    setHasUserEdits(false);
  }

  const text = (name: string): string => {
    const found = imported[name];
    return typeof found === "string" ? found : "";
  };
  const checked = (name: string): boolean => imported[name] === true;

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
    const importedKind = draft?.fields?.price_kind?.value;
    const priceKind =
      importedKind === "current_bid" ? "current_bid" : ("asking" as const);

    startTransition(async () => {
      try {
        const opportunity = await createOpportunity(
          {
            portfolio_id: portfolioId,
            source:
              mode === "manual"
                ? {
                    mode: "manual",
                    manual_identifier: String(data.get("manual_identifier")),
                    // Sans plateforme déclarée, l'analyse traiterait l'achat
                    // comme une vente de particulier à particulier et
                    // oublierait la commission.
                    platform_code:
                      String(data.get("platform_code") ?? "") || null,
                  }
                : {
                    // `assisted_import` quand les valeurs viennent d'un contenu
                    // collé : la responsabilité n'est pas la même que pour une
                    // page récupérée par le serveur.
                    mode:
                      draft?.access_mode === "assisted"
                        ? "assisted_import"
                        : "url",
                    url: url.trim(),
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
              ? {
                  amount,
                  currency: String(data.get("currency")),
                  // Une enchère en cours n'est pas un prix demandé : elle
                  // montera, et peut ne pas atteindre la réserve.
                  kind: priceKind,
                }
              : { kind: priceKind },
            ...(draft
              ? {
                  import_draft: {
                    platform_code: draft.platform_code,
                    fetched_at: draft.fetched_at ?? new Date().toISOString(),
                    access_mode: draft.access_mode,
                    fields: draft.fields ?? {},
                    warnings: draft.warnings ?? [],
                  },
                }
              : {}),
          },
          // Une création renvoyée après une coupure ne doit pas ouvrir un
          // second dossier. La contrainte d'unicité n'y suffit pas : rien
          // n'oblige à saisir un identifiant manuel ni une URL.
          { idempotencyKey: keyFor("create-opportunity") },
        );
        settle("create-opportunity");
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
      <form
        onSubmit={handleSubmit}
        onInput={markUserEdit}
        onChange={markUserEdit}
        className="space-y-5"
      >
        <div
          role="radiogroup"
          aria-label="Mode de saisie"
          className="inline-flex rounded-md border border-border p-0.5"
        >
          {(["manual", "url"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={mode === option}
              onClick={() => setMode(option)}
              className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === option
                  ? "bg-accent text-bg"
                  : "text-fg-muted hover:text-fg"
              }`}
            >
              {labels.sourceMode(option)}
            </button>
          ))}
        </div>

        {mode === "manual" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Identifiant manuel">
              <input
                name="manual_identifier"
                required
                className={inputClass}
                placeholder="LONGINES-2026-001"
              />
            </Field>
            <Field label="Plateforme d'achat">
              <select name="platform_code" className={inputClass}>
                <option value="">
                  Aucune — achat de particulier à particulier
                </option>
                {platforms.map((platform) => (
                  <option key={platform.code} value={platform.code}>
                    {platform.name}
                    {platform.hasRule ? "" : " (grille de frais manquante)"}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        ) : (
          <ListingPrefill
            url={url}
            onUrlChange={setUrl}
            onApply={applyPrefill}
            hasUserEdits={hasUserEdits}
          />
        )}

        <div className="grid grid-cols-2 gap-4">
          <Field label="Marque">
            <input
              key={`brand-${importVersion}`}
              name="brand"
              required
              defaultValue={text("brand")}
              className={inputClass}
            />
          </Field>
          <Field label="Référence">
            <input
              key={`reference-${importVersion}`}
              name="reference"
              required
              defaultValue={text("reference")}
              className={inputClass}
            />
          </Field>
        </div>
        {imported.reference !== undefined && (
          <p className="-mt-3 text-xs text-fg-muted">
            Référence reprise de l&apos;annonce : elle reste à confirmer, elle
            n&apos;est pas vérifiée.
          </p>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Field label="État mécanique">
            <select name="mechanical_condition" className={inputClass}>
              {options.mechanicalCondition.map((option) => (
                <option key={option} value={option}>
                  {labels.mechanicalCondition(option)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="État cosmétique">
            <select name="cosmetic_condition" className={inputClass}>
              {options.cosmeticCondition.map((option) => (
                <option key={option} value={option}>
                  {labels.cosmeticCondition(option)}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input
              key={`box-${importVersion}`}
              type="checkbox"
              name="box"
              defaultChecked={checked("box")}
              className="accent-accent"
            />
            Boîte
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              key={`papers-${importVersion}`}
              type="checkbox"
              name="papers"
              defaultChecked={checked("papers")}
              className="accent-accent"
            />
            Papiers
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Pays du vendeur">
            <input
              key={`country-${importVersion}`}
              name="country_code"
              maxLength={2}
              placeholder="FR"
              defaultValue={text("seller_country")}
              className={inputClass}
            />
          </Field>
          <Field label="Type de vendeur">
            <select
              key={`seller-type-${importVersion}`}
              name="seller_type"
              className={inputClass}
              defaultValue={text("seller_type")}
            >
              <option value="">—</option>
              {options.sellerType.map((option) => (
                <option key={option} value={option}>
                  {labels.sellerType(option)}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Prix (optionnel)">
            <input
              key={`amount-${importVersion}`}
              name="amount"
              inputMode="decimal"
              placeholder="1800.00"
              defaultValue={text("price_amount")}
              className={inputClass}
            />
          </Field>
          <Field label="Devise">
            <input
              key={`currency-${importVersion}`}
              name="currency"
              defaultValue={text("price_currency") || "EUR"}
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
