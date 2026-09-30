import type { components } from "@kairos/contracts";

/**
 * Le recalcul automatique de la cote et de l'analyse, côté écran.
 *
 * L'API recalcule seule quand un comparable est ajouté, importé, corrigé ou
 * exclu, et **dit ce qu'elle a fait** dans la réponse. Ce module ne décide de
 * rien : il traduit ce constat en phrase, et il prévient les autres panneaux
 * qu'il y a du neuf à relire.
 */

export type Recalculation = components["schemas"]["RecalculationResponse"];

/**
 * Signal envoyé aux panneaux de cote et d'analyse.
 *
 * Ils sont indépendants — chacun se charge à l'ouverture de la fiche — et une
 * fiche est un composant serveur : elle ne peut pas porter l'état qui les
 * relierait. Un événement du navigateur suffit, sans rien restructurer.
 */
export const MARKET_CHANGED_EVENT = "kairos:market-changed";

export function announceMarketChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(MARKET_CHANGED_EVENT));
}

/**
 * Une phrase qui dit la vérité sur ce qui a été calculé.
 *
 * Quatre issues, et jamais confondues : « pas assez de comparables » n'est pas
 * une panne, et « le calcul a échoué mais votre saisie est enregistrée » ne
 * doit pas se lire comme un succès.
 */
export function describeRecalculation(
  action: string,
  recalculation: Recalculation | null | undefined,
): string {
  if (!recalculation) return action;

  switch (recalculation.status) {
    case "recalculated":
      return `${action} La cote et l'analyse ont été recalculées automatiquement.`;
    case "valuation_only":
      return (
        `${action} La cote a été recalculée automatiquement, ` +
        `mais l'analyse n'a pas pu l'être` +
        (recalculation.detail ? ` : ${recalculation.detail}` : ".")
      );
    case "skipped":
      return `${action} Il faut au moins deux comparables pour calculer une cote.`;
    case "failed":
      return (
        `${action} Le calcul automatique a échoué` +
        (recalculation.detail ? ` : ${recalculation.detail}` : ".")
      );
  }
}

/** Y a-t-il quelque chose de neuf à relire dans les panneaux ? */
export function changedSomething(
  recalculation: Recalculation | null | undefined,
): boolean {
  return (
    recalculation?.status === "recalculated" ||
    recalculation?.status === "valuation_only"
  );
}
