import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MARKET_CHANGED_EVENT,
  announceMarketChange,
  changedSomething,
  describeRecalculation,
  type Recalculation,
} from "./recalculation";

/**
 * Le recalcul automatique dit ce qu'il a fait ; l'écran doit le répéter sans le
 * déformer. Quatre issues, et jamais confondues : « pas assez de comparables »
 * n'est pas une panne, et « le calcul a échoué » ne doit pas se lire comme un
 * succès.
 */

const ACTION = "Comparable ajouté.";

function outcome(partial: Partial<Recalculation> & Pick<Recalculation, "status">) {
  return partial as Recalculation;
}

describe("describeRecalculation", () => {
  it("laisse la phrase telle quelle quand l'API n'a rien recalculé", () => {
    // Une correction sans opportunité désignée : pas de recalcul, pas de promesse.
    expect(describeRecalculation(ACTION, null)).toBe(ACTION);
    expect(describeRecalculation(ACTION, undefined)).toBe(ACTION);
  });

  it("annonce un recalcul complet", () => {
    const text = describeRecalculation(ACTION, outcome({ status: "recalculated" }));
    expect(text).toContain("recalculées automatiquement");
  });

  it("dit que l'analyse manque, et pourquoi, quand seule la cote a suivi", () => {
    const text = describeRecalculation(
      ACTION,
      outcome({
        status: "valuation_only",
        detail: "Un portefeuille sans capital ne permet aucun calcul d'exposition.",
      }),
    );
    expect(text).toContain("La cote a été recalculée");
    expect(text).toContain("l'analyse n'a pas pu l'être");
    expect(text).toContain("sans capital");
  });

  it("ne présente pas « pas assez de comparables » comme une panne", () => {
    const text = describeRecalculation(ACTION, outcome({ status: "skipped" }));
    expect(text).toContain("au moins deux comparables");
    expect(text).not.toMatch(/échoué|erreur/i);
  });

  it("ne fait pas passer un échec pour un succès", () => {
    const text = describeRecalculation(
      ACTION,
      outcome({ status: "failed", detail: "Le recalcul automatique a échoué." }),
    );
    expect(text).toContain("a échoué");
    expect(text).not.toContain("recalculées automatiquement");
  });
});

describe("changedSomething", () => {
  it("ne relit les panneaux que s'il y a du neuf", () => {
    expect(changedSomething(outcome({ status: "recalculated" }))).toBe(true);
    expect(changedSomething(outcome({ status: "valuation_only" }))).toBe(true);
    expect(changedSomething(outcome({ status: "skipped" }))).toBe(false);
    expect(changedSomething(outcome({ status: "failed" }))).toBe(false);
    expect(changedSomething(null)).toBe(false);
    expect(changedSomething(undefined)).toBe(false);
  });
});

describe("announceMarketChange", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("ne plante pas hors navigateur", () => {
    // Rendu serveur : `window` n'existe pas.
    expect(() => announceMarketChange()).not.toThrow();
  });

  it("émet l'événement que les panneaux écoutent", () => {
    const dispatched: string[] = [];
    vi.stubGlobal("window", {
      dispatchEvent: (event: Event) => dispatched.push(event.type),
    });
    announceMarketChange();
    expect(dispatched).toEqual([MARKET_CHANGED_EVENT]);
  });
});
