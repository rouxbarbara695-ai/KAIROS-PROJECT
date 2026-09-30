import type { MarketSearchRun, MarketSearchSource } from "@/lib/api";

/**
 * La recherche autonome de comparables, dite en français.
 *
 * Ce module ne décide de rien : il traduit ce que l'API a constaté. Un échec
 * reste un échec avec son diagnostic ; « aucune annonce » ne se confond jamais
 * avec « la source n'a pas répondu ».
 */

export const REJECTION_LABELS: Record<string, string> = {
  reference_not_stated:
    "Référence exacte absente du titre (annonce voisine, non substituée)",
  brand_not_stated: "Marque absente du titre",
  counterfeit_marker: "Le titre évoque une copie",
  not_a_complete_watch: "Pièce détachée, accessoire seul ou montre à réparer",
  multiple_items: "Plusieurs montres sous un seul prix",
  no_price: "Aucun prix exploitable",
  auction_end_unknown: "Enchère sans heure de clôture",
  auction_already_ended: "Enchère terminée",
  auction_too_early: "Enchère loin de sa clôture : la mise n'est pas un prix",
  auction_without_bids: "Enchère sans aucune mise",
};

export const SOURCE_NAMES: Record<string, string> = { ebay: "eBay" };

export const SOURCE_STATUS_LABELS: Record<string, string> = {
  ok: "Interrogée",
  not_configured: "Non configurée",
  blocked: "Accès refusé",
  rate_limited: "Quota atteint",
  budget_exhausted: "Limite atteinte",
  error: "En erreur",
};

export function sourceName(code: string): string {
  return SOURCE_NAMES[code] ?? code;
}

export function rejectionLabel(code: string): string {
  return REJECTION_LABELS[code] ?? code;
}

export function isActive(run: MarketSearchRun | null | undefined): boolean {
  return run?.status === "queued" || run?.status === "running";
}

/**
 * Âge des données, toujours dit : les conditions de l'API eBay exigent d'en
 * indiquer l'âge au-delà de six heures, et un chiffre ancien présenté comme
 * frais est un mensonge.
 */
export function describeFreshness(
  ageMinutes: number | null | undefined,
  stale: boolean,
): string {
  if (ageMinutes === null || ageMinutes === undefined) return "";
  let age: string;
  if (ageMinutes < 1) age = "à l'instant";
  else if (ageMinutes < 60) age = `il y a ${ageMinutes} min`;
  else if (ageMinutes < 60 * 48) age = `il y a ${Math.round(ageMinutes / 60)} h`;
  else age = `il y a ${Math.round(ageMinutes / (60 * 24))} jours`;
  return stale ? `Relevé ${age} — données anciennes` : `Relevé ${age}`;
}

/** La phrase qui résume ce que la recherche a trouvé. */
export function headline(run: MarketSearchRun): string {
  if (run.status === "queued") return "Recherche en attente…";
  if (run.status === "running") {
    return run.summary.stage === "recalculating"
      ? "Calcul de la cote…"
      : "Recherche en cours…";
  }
  const recorded = run.summary.comparables_recorded;
  const known = run.summary.comparables_known_for_reference ?? 0;
  if (run.summary.insufficient_data) {
    return (
      run.summary.insufficient_data_message ??
      "Données insuffisantes : aucune estimation n'est produite."
    );
  }
  if (run.status === "failed") {
    return "La recherche n'a rien pu obtenir. Aucune donnée existante n'a été effacée.";
  }
  if (recorded > 0) {
    return `${recorded} nouveau${recorded > 1 ? "x" : ""} comparable${
      recorded > 1 ? "s" : ""
    } exact${recorded > 1 ? "s" : ""} ajouté${recorded > 1 ? "s" : ""} (${known} au total pour cette référence).`;
  }
  return `Aucun nouveau comparable exact (${known} déjà connu${
    known > 1 ? "s" : ""
  } pour cette référence).`;
}

/** Ce qu'une source a lu, retenu et écarté, en une ligne. */
export function describeSourceCounts(source: MarketSearchSource): string {
  if (source.status !== "ok" && source.read === 0) return "";
  const rejected = Object.values(source.rejected).reduce((a, b) => a + b, 0);
  const parts = [
    `${source.read} annonce${source.read > 1 ? "s" : ""} lue${
      source.read > 1 ? "s" : ""
    }`,
    `${source.recorded} retenue${source.recorded > 1 ? "s" : ""}`,
    `${rejected} écartée${rejected > 1 ? "s" : ""}`,
  ];
  if (source.already_known > 0) parts.push(`${source.already_known} déjà connue(s)`);
  if (source.duplicates > 0) parts.push(`${source.duplicates} doublon(s) fusionné(s)`);
  if (source.fx_unavailable > 0)
    parts.push(`${source.fx_unavailable} sans taux de change`);
  return parts.join(" · ");
}

/** Heure à laquelle une actualisation redevient possible, si elle ne l'est pas. */
export function refreshBlockedUntil(
  run: MarketSearchRun | null | undefined,
  now: Date = new Date(),
): Date | null {
  if (!run?.next_refresh_allowed_at) return null;
  const at = new Date(run.next_refresh_allowed_at);
  return at.getTime() > now.getTime() ? at : null;
}
