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

const AUDIT_ACTION: Record<string, string> = {
  correct: "Correction",
  exclude: "Exclusion",
  reinstate: "Réintégration",
  create: "Création",
};

const AUDIT_RESOURCE: Record<string, string> = {
  opportunity: "Opportunité",
  watch: "Montre",
  seller: "Vendeur",
};

const PRICE_KIND: Record<string, string> = {
  asking: "Prix demandé",
  offer: "Offre",
  accepted_offer: "Offre acceptée",
  current_bid: "Enchère courante",
  hammer: "Prix marteau",
  realized: "Prix réalisé",
  external_estimate: "Estimation externe",
  kairos_estimate: "Estimation KAIROS",
};

const RECOMMENDATION: Record<string, string> = {
  buy: "Acheter",
  watch: "Surveiller",
  pass: "Passer",
  analysis_impossible: "Analyse impossible",
};

const GATE: Record<string, string> = {
  G1_AUTHENTICITY: "Authenticité",
  G2_IDENTIFICATION: "Identification",
  G3_DATA_QUALITY: "Qualité des données",
  G4_MARKET_SUPPORT: "Support de marché",
  G5_SELLER_RISK: "Risque vendeur",
};

const GATE_STATUS: Record<string, string> = {
  passed: "Passée",
  passed_with_warning: "Passée avec réserve",
  failed: "Bloquante",
  not_evaluated: "Non évaluée",
};

/**
 * Motifs de porte, en clair.
 *
 * Un code brut affiché tel quel demande à l'utilisateur de deviner ce qui
 * bloque son dossier. La règle 6 veut le motif, pas seulement le verdict.
 */
const GATE_REASON: Record<string, string> = {
  reference_not_confirmed: "Référence non confirmée",
  reference_suggested_not_confirmed:
    "Référence suggérée, pas encore confirmée par un humain",
  identification_confidence_below_threshold:
    "Confiance d'identification sous le seuil",
  price_missing: "Prix absent",
  currency_missing: "Devise absente",
  condition_missing: "État non renseigné",
  completeness_missing: "Complétude non renseignée",
  seller_country_missing: "Pays du vendeur absent",
  insufficient_comparables: "Trop peu de comparables",
  total_weight_not_positive: "Aucun comparable ne pèse dans la cote",
  seller_risk_high: "Vendeur à risque élevé",
  seller_risk_medium: "Vendeur à risque moyen",
  seller_risk_unknown: "Vendeur inconnu",
};

const PILLAR: Record<string, string> = {
  profitability: "Rentabilité",
  liquidity: "Liquidité",
  portfolio: "Portefeuille",
  condition: "État",
  evidence_quality: "Qualité des preuves",
};

const SUBSCORE: Record<string, string> = {
  profit: "Profit central",
  roi: "ROI central",
  delay: "Délai de revente",
  depth: "Profondeur du marché",
  consistency: "Cohérence des prix",
  cash_impact: "Impact trésorerie",
  diversification: "Diversification",
  immobilization: "Immobilisation",
  mechanical: "Mécanique",
  cosmetic: "Cosmétique",
  completeness: "Complétude",
  originality: "Originalité",
  listing: "Qualité de la fiche",
  comparables: "Qualité des comparables",
  seller: "Fiabilité du vendeur",
  protections: "Protections",
};

const CAP: Record<string, string> = {
  valuation_below_40: "Cote peu fiable (confiance < 40)",
  valuation_below_60: "Cote incertaine (confiance < 60)",
  evidence_below_40: "Preuves insuffisantes",
  allocation_exceeded: "Allocation au-delà du maximum de la stratégie",
  immobilization_and_allocation:
    "Capital immobilisé et allocation élevée simultanément",
  immobilization_relieved_exceptional_deal:
    "Dérogation au plafond d'immobilisation — affaire exceptionnelle",
  illiquid_diversification: "Diversification plafonnée par la faible liquidité",
};

const SCENARIO: Record<string, string> = {
  prudent: "Prudent",
  central: "Central",
  favorable: "Favorable",
};

const BINDING_CONSTRAINT: Record<string, string> = {
  profit: "Profit minimal",
  roi: "ROI minimal",
  infeasible: "Aucun prix ne tient les contraintes",
};

const RECORD_FIELD: Record<string, string> = {
  brand: "Marque",
  reference: "Référence",
  reference_status: "Référence confirmée",
  mechanical_condition: "État mécanique",
  cosmetic_condition: "État cosmétique",
  originality: "Originalité",
  box: "Boîte",
  papers: "Papiers",
  price: "Prix",
  seller_country: "Pays du vendeur",
  seller_type: "Type de vendeur",
  platform: "Plateforme",
};

function translate(
  dictionary: Record<string, string>,
  value: string | null | undefined,
): string {
  if (!value) return "—";
  return dictionary[value] ?? value;
}

export const labels = {
  recommendation: (value: string | null | undefined) =>
    translate(RECOMMENDATION, value),
  gate: (value: string | null | undefined) => translate(GATE, value),
  gateStatus: (value: string | null | undefined) => translate(GATE_STATUS, value),
  gateReason: (value: string | null | undefined) => translate(GATE_REASON, value),
  pillar: (value: string | null | undefined) => translate(PILLAR, value),
  subscore: (value: string | null | undefined) => translate(SUBSCORE, value),
  cap: (value: string | null | undefined) => translate(CAP, value),
  scenario: (value: string | null | undefined) => translate(SCENARIO, value),
  bindingConstraint: (value: string | null | undefined) =>
    translate(BINDING_CONSTRAINT, value),
  recordField: (value: string | null | undefined) =>
    translate(RECORD_FIELD, value),
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
  auditAction: (value: string | null | undefined) =>
    translate(AUDIT_ACTION, value),
  auditResource: (value: string | null | undefined) =>
    translate(AUDIT_RESOURCE, value),
  priceKind: (value: string | null | undefined) =>
    translate(PRICE_KIND, value),
};

/** Types de prix saisissables manuellement (`PriceInputCreate`). */
export const PRICE_KIND_OPTIONS = [
  "asking",
  "offer",
  "accepted_offer",
  "current_bid",
  "hammer",
] as const;

/** Horodatage lisible, en heure locale. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

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
