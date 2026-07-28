/**
 * Libellés visibles par l'utilisateur.
 *
 * Les vocabulaires métier restent en anglais dans l'API, la base et le
 * ruleset : ce module ne traduit que l'affichage. Une valeur inconnue est
 * rendue telle quelle plutôt que masquée — un vocabulaire élargi côté API
 * doit rester visible, pas disparaître silencieusement de l'écran.
 */

const OPPORTUNITY_STATUS: Record<string, string> = {
  watching: "En veille",
  buy: "À acheter",
  auction: "Enchère en cours",
  purchased: "Achetée",
  in_stock: "En stock",
  listed_for_sale: "En vente",
  awaiting_buyer_payment: "Paiement attendu",
  awaiting_payout: "Reversement attendu",
  sold: "Vendue",
  abandoned: "Abandonnée",
};

const REFERENCE_STATUS: Record<string, string> = {
  unconfirmed: "Non confirmée",
  suggested: "Suggérée",
  confirmed: "Confirmée",
  corrected: "Corrigée",
  unknown: "Inconnue",
};

const MECHANICAL_CONDITION: Record<string, string> = {
  verified: "Vérifié",
  functional: "Fonctionnel",
  unknown: "Inconnu",
  defect: "Défaut constaté",
};

const COSMETIC_CONDITION: Record<string, string> = {
  excellent: "Excellent",
  very_good: "Très bon",
  good: "Bon",
  fair: "Moyen",
  poor: "Mauvais",
};

const COMPLETENESS_LEVEL: Record<string, string> = {
  full_set: "Full set",
  box_or_papers: "Boîte ou papiers",
  watch_only: "Montre seule",
};

const ORIGINALITY_LEVEL: Record<string, string> = {
  original: "D'origine",
  uncertain: "Incertaine",
  major_modification: "Modification majeure",
};

const SELLER_TYPE: Record<string, string> = {
  private: "Particulier",
  professional: "Professionnel",
  unknown: "Inconnu",
};

const SOURCE_MODE: Record<string, string> = {
  manual: "Saisie manuelle",
  url: "Annonce en ligne",
  assisted_import: "Import assisté",
  connector: "Collecteur",
};

function translate(
  dictionary: Record<string, string>,
  value: string | null | undefined,
): string {
  if (!value) return "—";
  return dictionary[value] ?? value;
}

export const labels = {
  opportunityStatus: (value: string | null | undefined) =>
    translate(OPPORTUNITY_STATUS, value),
  referenceStatus: (value: string | null | undefined) =>
    translate(REFERENCE_STATUS, value),
  mechanicalCondition: (value: string | null | undefined) =>
    translate(MECHANICAL_CONDITION, value),
  cosmeticCondition: (value: string | null | undefined) =>
    translate(COSMETIC_CONDITION, value),
  completenessLevel: (value: string | null | undefined) =>
    translate(COMPLETENESS_LEVEL, value),
  originalityLevel: (value: string | null | undefined) =>
    translate(ORIGINALITY_LEVEL, value),
  sellerType: (value: string | null | undefined) =>
    translate(SELLER_TYPE, value),
  sourceMode: (value: string | null | undefined) =>
    translate(SOURCE_MODE, value),
};

/** Options proposées dans les formulaires, dans l'ordre du vocabulaire. */
export const options = {
  mechanicalCondition: ["verified", "functional", "unknown", "defect"],
  cosmeticCondition: ["excellent", "very_good", "good", "fair", "poor"],
  sellerType: ["private", "professional", "unknown"],
} as const;

/**
 * Formate un montant transporté sous forme de chaîne décimale.
 *
 * Le nombre de décimales affichées est celui reçu de l'API : le formatage
 * ne doit ni arrondir ni compléter un montant, seulement le rendre lisible.
 * Une devise inconnue ou un montant non numérique retombent sur la valeur
 * brute plutôt que de masquer l'information.
 */
export function formatAmount(
  amount: string | null | undefined,
  currency: string | null | undefined,
): string {
  if (!amount) return "—";
  if (!currency) return amount;

  const parsed = Number(amount);
  if (!Number.isFinite(parsed)) return `${amount} ${currency}`;

  const separator = amount.indexOf(".");
  const decimals = separator === -1 ? 0 : amount.length - separator - 1;

  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      minimumFractionDigits: Math.min(decimals, 20),
      maximumFractionDigits: Math.min(decimals, 20),
    }).format(parsed);
  } catch {
    return `${amount} ${currency}`;
  }
}
