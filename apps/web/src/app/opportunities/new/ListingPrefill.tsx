"use client";

import { useState } from "react";
import {
  ApiError,
  platformAccess,
  prefillListing,
  prefillListingFromContent,
  type ImportedField,
  type ListingPrefillResponse,
} from "@/lib/api";

/**
 * « Je colle un lien, KAIROS remplit ce qu'il peut. »
 *
 * Trois choses gouvernent cet écran, et elles vont dans le même sens : ne
 * jamais laisser croire qu'une valeur est plus sûre qu'elle ne l'est.
 *
 * - **Rien n'est appliqué sans que l'utilisateur voie quoi.** Le résultat
 *   s'affiche avant d'entrer dans le formulaire, avec l'origine de chaque
 *   valeur et ce que la page ne disait pas.
 * - **Un échec conserve le lien et la saisie déjà faite.** L'utilisateur ne
 *   recolle rien, ne ressaisit rien, et se voit proposer le repli qui
 *   correspond au blocage réel.
 * - **Une correction ne se fait pas écraser.** Une seconde récupération
 *   prévient avant de remplacer ce qui a été corrigé à la main.
 */

const inputClass =
  "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

type Phase =
  | { step: "idle" }
  | { step: "detecting" }
  | { step: "fetching"; platform: string }
  | { step: "done"; result: ListingPrefillResponse }
  | { step: "error"; message: string };

const PLATFORM_LABELS: Record<string, string> = {
  chrono24: "Chrono24",
  catawiki: "Catawiki",
  vestiaire_collective: "Vestiaire Collective",
  watchfinder: "Watchfinder",
  watchcharts: "WatchCharts",
  ebay: "eBay",
  independent_boutique: "site indépendant",
};

function platformLabel(code: string): string {
  return PLATFORM_LABELS[code] ?? code;
}

/** Champs trop verbeux ou redondants pour l'aperçu. Ils restent dans la
 *  trace conservée avec le dossier — ils ne sont simplement pas listés ici. */
const HIDDEN_IN_PREVIEW = new Set([
  "title",
  "description",
  "external_id",
  "price_kind",
  "price_amount",
  "price_currency",
  "shipping",
  "insurance",
  "warranty",
  "returns",
  "buckle",
  "replaced_parts",
  "service_history",
]);

const FIELD_LABELS: Record<string, string> = {
  brand: "Marque",
  collection: "Modèle",
  reference: "Référence",
  year: "Année",
  movement: "Mouvement",
  calibre: "Calibre",
  case_material: "Matériau du boîtier",
  case_diameter_mm: "Diamètre",
  dial: "Cadran",
  bracelet_material: "Bracelet",
  box: "Boîte",
  papers: "Papiers",
  price_amount: "Prix",
  price_currency: "Devise",
  seller_type: "Type de vendeur",
  seller_country: "Pays du vendeur",
  seller_name: "Vendeur",
  seller_since: "Vendeur depuis",
  lot_number: "Numéro de lot",
  current_bid_amount: "Enchère en cours",
  current_bid_currency: "Devise de l'enchère",
  bid_count: "Nombre d'enchères",
  closing_at: "Clôture",
  closing_timezone: "Fuseau",
  estimate_low: "Estimation Catawiki (bas)",
  estimate_high: "Estimation Catawiki (haut)",
  estimate_currency: "Devise de l'estimation",
  reserve_status: "Prix de réserve",
  shipping_cost_amount: "Livraison vers la France",
  shipping_destination: "Destination des frais",
  declared_condition: "État déclaré",
};

/** Valeurs codées côté API, rendues lisibles à l'écran. */
const VALUE_LABELS: Record<string, string> = {
  current_bid: "enchère en cours",
  asking: "prix demandé",
  no_reserve: "aucun prix de réserve",
  not_met: "non atteint",
  met: "atteint",
};

function displayValue(field: ImportedField): string {
  if (field.provenance === "absent") return "Non renseigné";
  if (field.value === null || field.value === undefined) {
    return field.raw ?? "Non renseigné";
  }
  if (typeof field.value === "boolean") return field.value ? "Oui" : "Non";
  const text = String(field.value);
  return VALUE_LABELS[text] ?? text;
}

export function ListingPrefill({
  url,
  onUrlChange,
  onApply,
  hasUserEdits,
}: {
  url: string;
  onUrlChange: (url: string) => void;
  onApply: (result: ListingPrefillResponse) => void;
  hasUserEdits: boolean;
}) {
  const [phase, setPhase] = useState<Phase>({ step: "idle" });
  const [pasted, setPasted] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [access, setAccess] = useState<{
    platform: string;
    mode: string;
    explanation: string;
  } | null>(null);

  const busy = phase.step === "detecting" || phase.step === "fetching";
  // Catawiki est le cas courant : sa page ne se récupère pas, l'import passe
  // par le collage. Le dire avant que l'utilisateur clique lui épargne un
  // aller-retour pour un refus dont on connaît déjà l'issue.
  const pasteOnly = access?.mode === "assisted";

  async function checkAccess(candidate: string) {
    setAccess(null);
    if (!candidate.trim().startsWith("http")) return;
    try {
      const result = await platformAccess(candidate.trim());
      setAccess({
        platform: result.platform_code,
        mode: result.access_mode,
        explanation: result.explanation,
      });
      setShowPaste(result.access_mode === "assisted");
    } catch {
      // Sans réponse, on ne présume rien : le bouton reste disponible.
      setAccess(null);
    }
  }

  async function run(fetchIt: () => Promise<ListingPrefillResponse>) {
    setPhase({ step: "detecting" });
    try {
      const result = await fetchIt();
      setPhase({ step: "done", result });
      // Le repli s'ouvre tout seul quand c'est lui qu'il faut : l'utilisateur
      // n'a pas à deviner qu'une autre voie existe.
      setShowPaste(!result.succeeded && result.access_mode === "assisted");
    } catch (err) {
      // Le lien saisi n'est jamais effacé par un échec.
      setPhase({
        step: "error",
        message:
          err instanceof ApiError
            ? err.message
            : "La récupération a échoué. Le lien est conservé.",
      });
    }
  }

  function retrieve() {
    if (!url.trim()) return;
    void run(async () => {
      setPhase({ step: "fetching", platform: "" });
      return prefillListing(url.trim());
    });
  }

  function importPasted() {
    if (!pasted.trim()) return;
    void run(() => prefillListingFromContent(url.trim(), pasted));
  }

  function apply(result: ListingPrefillResponse) {
    if (
      hasUserEdits &&
      !window.confirm(
        "Des champs ont déjà été corrigés à la main. Les remplacer par les " +
          "valeurs importées ?",
      )
    ) {
      return;
    }
    onApply(result);
  }

  return (
    // Marqué pour que le formulaire ne prenne pas la saisie du lien ni le
    // collage pour des corrections de champs : sans cela, le tout premier
    // import demanderait de confirmer un écrasement qui n'a pas lieu d'être.
    <div
      data-import-panel
      className="space-y-3 rounded-md border border-border bg-surface p-4"
    >
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-fg-muted">
          Lien de l&apos;annonce
        </span>
        <div className="flex gap-2">
          <input
            type="url"
            value={url}
            onChange={(event) => onUrlChange(event.target.value)}
            onBlur={(event) => void checkAccess(event.target.value)}
            className={inputClass}
            placeholder="https://www.catawiki.com/fr/l/12345678-…"
          />
          {!pasteOnly && (
            <button
              type="button"
              onClick={retrieve}
              disabled={busy || !url.trim()}
              className="shrink-0 rounded-md bg-accent px-3 py-2 text-sm font-medium text-bg disabled:opacity-50"
            >
              {busy ? "Récupération…" : "Récupérer les informations"}
            </button>
          )}
        </div>
      </label>

      {access && pasteOnly && (
        <p className="text-sm text-fg-muted">{access.explanation}</p>
      )}

      {phase.step === "detecting" && (
        <p className="text-sm text-fg-muted" role="status">
          Reconnaissance de la plateforme…
        </p>
      )}
      {phase.step === "fetching" && (
        <p className="text-sm text-fg-muted" role="status">
          Lecture de l&apos;annonce…
        </p>
      )}

      {phase.step === "error" && (
        <p className="text-sm text-danger">{phase.message}</p>
      )}

      {phase.step === "done" && !phase.result.succeeded && (
        <div className="space-y-2 rounded-md border border-border bg-bg p-3">
          <p className="text-sm">
            {phase.result.failure?.message ?? "L'annonce n'a pas pu être lue."}
          </p>
          <p className="text-xs text-fg-muted">
            Plateforme reconnue : {platformLabel(phase.result.platform_code)}.
            Le lien est conservé, la saisie aussi.
          </p>
        </div>
      )}

      {phase.step === "done" && phase.result.succeeded && (
        <PrefillPreview
          result={phase.result}
          onApply={() => apply(phase.result)}
        />
      )}

      {(showPaste || phase.step === "error") && (
        <details
          open={showPaste}
          className="rounded-md border border-border bg-bg p-3"
        >
          <summary className="cursor-pointer text-sm font-medium">
            {pasteOnly
              ? "Coller le contenu de l'annonce"
              : "Import assisté — coller le contenu de la page"}
          </summary>
          <div className="mt-3 space-y-2">
            <ol className="list-decimal space-y-1 pl-4 text-xs text-fg-muted">
              <li>Ouvrir le lot dans un autre onglet.</li>
              <li>
                Tout sélectionner (<kbd>Ctrl</kbd>+<kbd>A</kbd>), copier (
                <kbd>Ctrl</kbd>+<kbd>C</kbd>).
              </li>
              <li>Coller ci-dessous.</li>
            </ol>
            <p className="text-xs text-fg-muted">
              Le texte visible suffit : ni code source, ni outils de
              développement. Les photos ne suivent pas — elles restent
              consultables sur la plateforme par le lien.
            </p>
            <textarea
              value={pasted}
              onChange={(event) => setPasted(event.target.value)}
              rows={5}
              className={`${inputClass} font-mono text-xs`}
              placeholder="Contenu de la page…"
            />
            <button
              type="button"
              onClick={importPasted}
              disabled={busy || !pasted.trim()}
              className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Analyser ce contenu
            </button>
          </div>
        </details>
      )}
    </div>
  );
}

function PrefillPreview({
  result,
  onApply,
}: {
  result: ListingPrefillResponse;
  onApply: () => void;
}) {
  const entries = Object.entries(result.fields ?? {}).filter(
    ([name]) => !HIDDEN_IN_PREVIEW.has(name),
  );
  const warnings = result.warnings ?? [];
  const read = entries.filter(([, field]) => field.provenance !== "absent");
  const missing = entries.filter(([, field]) => field.provenance === "absent");

  return (
    <div className="space-y-3 rounded-md border border-border bg-bg p-3">
      <p className="text-sm">
        {read.length} champ{read.length > 1 ? "s" : ""} lu
        {read.length > 1 ? "s" : ""} sur {platformLabel(result.platform_code)}
        {result.access_mode === "assisted" && " (contenu que vous avez fourni)"}
        . À vérifier avant enregistrement.
      </p>

      {read.length > 0 && (
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          {read.map(([name, field]) => (
            <div key={name} className="flex justify-between gap-2">
              <dt className="text-fg-muted">{FIELD_LABELS[name] ?? name}</dt>
              <dd className="text-right">{displayValue(field)}</dd>
            </div>
          ))}
        </dl>
      )}

      {missing.length > 0 && (
        <p className="text-xs text-fg-muted">
          Non renseigné par l&apos;annonce, à saisir :{" "}
          {missing.map(([name]) => FIELD_LABELS[name] ?? name).join(", ")}.
        </p>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1 text-xs text-fg-muted">
          {warnings.map((warning) => (
            <li key={warning}>— {warning}</li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={onApply}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg"
      >
        Reprendre ces valeurs dans le formulaire
      </button>
    </div>
  );
}
