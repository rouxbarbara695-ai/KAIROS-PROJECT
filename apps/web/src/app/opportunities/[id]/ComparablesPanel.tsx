"use client";

import { useEffect, useState, useTransition, type FormEvent } from "react";
import {
  ApiError,
  createComparable,
  createOverride,
  importComparables,
  listComparables,
  type ComparableResponse,
} from "@/lib/api";
import { Disclosure } from "@/components/Disclosure";
import { formatAmount, labels, options, PRICE_KIND_OPTIONS } from "@/lib/labels";

const inputClass =
  "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

const RELIABILITY_LABELS: Record<string, string> = {
  a: "A — transaction confirmée",
  b: "B — marchand reconnu",
  c: "C — annonce observée",
  d: "D — dernier prix demandé",
  e: "E — donnée non vérifiée",
};

const MARKET_STATUS_LABELS: Record<string, string> = {
  active: "Annonce active",
  sold: "Vendue",
  ended: "Terminée",
  removed: "Retirée",
  unknown: "Inconnu",
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-fg-muted">{label}</span>
      {children}
    </label>
  );
}

export function ComparablesPanel({
  opportunityId,
  referenceConfirmed,
}: {
  opportunityId: string;
  referenceConfirmed: boolean;
}) {
  const [items, setItems] = useState<ComparableResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function refresh() {
    try {
      const page = await listComparables(opportunityId);
      setItems(page.items);
    } catch {
      setError("Impossible de charger les comparables.");
    }
  }

  useEffect(() => {
    void refresh();
    // La liste ne dépend que de l'opportunité affichée.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opportunityId]);

  function run(action: () => Promise<unknown>, success?: string) {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      try {
        await action();
        await refresh();
        if (success) setNotice(success);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "L'opération a échoué.",
        );
      }
    });
  }

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    run(async () => {
      await createComparable(opportunityId, {
        source_name: String(data.get("source_name")),
        seller_fingerprint: String(data.get("seller_fingerprint") || "") || null,
        price_kind: String(data.get("price_kind")) as "asking",
        amount: String(data.get("amount")),
        currency: String(data.get("currency")),
        market_status: String(data.get("market_status")) as "active",
        observed_at: new Date().toISOString(),
        source_reliability: String(data.get("source_reliability")) as "c",
        mechanical_condition: String(data.get("mechanical_condition")),
        cosmetic_condition: String(data.get("cosmetic_condition")),
        box: data.get("box") === "on",
        papers: data.get("papers") === "on",
      });
      form.reset();
    }, "Comparable ajouté.");
  }

  function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setError("Sélectionnez un fichier CSV.");
      return;
    }

    run(async () => {
      // Le fichier est lu ici : l'API reçoit du texte, pas du multipart.
      const content = await file.text();
      const result = await importComparables(opportunityId, content);
      form.reset();
      const rejected = result.rejected.length;
      setNotice(
        rejected === 0
          ? `${result.imported} comparable(s) importé(s).`
          : `${result.imported} importé(s), ${rejected} ligne(s) rejetée(s) : ` +
            result.rejected
              .map((row) => `ligne ${row.line} — ${row.error}`)
              .join(" ; "),
      );
    });
  }

  function toggleExclusion(comparable: ComparableResponse) {
    const reason = window.prompt(
      comparable.excluded
        ? "Motif de la réintégration"
        : "Motif de l'exclusion",
    );
    if (!reason?.trim()) return;

    run(
      () =>
        createOverride(comparable.id, {
          excluded: !comparable.excluded,
          ...(comparable.excluded ? {} : { exclusion_reason: reason }),
          reason,
        }),
      comparable.excluded ? "Comparable réintégré." : "Comparable exclu.",
    );
  }

  if (!referenceConfirmed) {
    return (
      <p className="text-sm text-fg-muted">
        Confirmez d&rsquo;abord la référence de la montre : un comparable doit
        se rattacher à une référence identifiée.
      </p>
    );
  }

  const retained = items.filter((item) => !item.excluded).length;

  return (
    <div className="space-y-4">
      <p className="text-sm text-fg-muted">
        {items.length === 0
          ? "Aucun comparable. Il en faut au moins deux pour calculer une cote."
          : `${retained} retenu(s) sur ${items.length}.`}
      </p>

      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-fg-muted">
                <th className="pb-2 font-medium">Source</th>
                <th className="pb-2 font-medium">Nature</th>
                <th className="pb-2 pr-4 text-right font-medium">Coût acheteur</th>
                <th className="pb-2 pr-4 font-medium">Preuve</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className={`border-b border-border last:border-0 ${
                    item.excluded ? "opacity-50" : ""
                  }`}
                >
                  <td className="py-2">
                    {item.source_name}
                    {item.excluded && item.exclusion_reason && (
                      <span className="ml-2 text-xs text-danger">
                        exclu — {item.exclusion_reason}
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-xs text-fg-muted">
                    {labels.priceKind(item.price_kind)} ·{" "}
                    {MARKET_STATUS_LABELS[item.market_status] ??
                      item.market_status}
                  </td>
                  <td className="numeric py-2 pr-4 text-right">
                    {formatAmount(item.buyer_total_price_eur, "EUR")}
                  </td>
                  <td className="py-2 pr-4 text-xs uppercase text-fg-muted">
                    {item.source_reliability}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => toggleExclusion(item)}
                      disabled={isPending}
                      className="text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline disabled:opacity-50"
                    >
                      {item.excluded ? "Réintégrer" : "Exclure"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {notice && <p className="text-sm text-accent-strong">{notice}</p>}
      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="space-y-2 border-t border-border pt-3">
        <Disclosure summary="Ajouter un comparable">
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Source">
                <input name="source_name" required className={inputClass} />
              </Field>
              <Field label="Empreinte vendeur">
                <input
                  name="seller_fingerprint"
                  className={inputClass}
                  placeholder="pour détecter les doublons"
                />
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Nature du prix">
                <select name="price_kind" className={inputClass}>
                  {PRICE_KIND_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {labels.priceKind(option)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Montant">
                <input
                  name="amount"
                  required
                  inputMode="decimal"
                  className={inputClass}
                  placeholder="3000.00"
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
            <div className="grid grid-cols-2 gap-3">
              <Field label="Qualité de la preuve">
                <select
                  name="source_reliability"
                  className={inputClass}
                  defaultValue="c"
                >
                  {Object.entries(RELIABILITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="État de l'annonce">
                <select name="market_status" className={inputClass}>
                  {Object.entries(MARKET_STATUS_LABELS).map(
                    ([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ),
                  )}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
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
            <button
              type="submit"
              disabled={isPending}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
            >
              Ajouter
            </button>
          </form>
        </Disclosure>

        <Disclosure summary="Importer un CSV">
          <form onSubmit={handleImport} className="space-y-3">
            <p className="text-xs text-fg-muted">
              Colonnes attendues : <code>source_name</code>,{" "}
              <code>price_kind</code>, <code>amount</code>,{" "}
              <code>currency</code>, <code>source_reliability</code>. Les
              colonnes inconnues sont ignorées.
            </p>
            <input
              type="file"
              name="file"
              accept=".csv,text/csv"
              required
              className="block w-full text-sm text-fg-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface-hover file:px-3 file:py-1.5 file:text-sm file:text-fg"
            />
            <button
              type="submit"
              disabled={isPending}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Importer
            </button>
          </form>
        </Disclosure>
      </div>
    </div>
  );
}
