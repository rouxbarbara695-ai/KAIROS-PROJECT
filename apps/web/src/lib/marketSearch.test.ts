import { describe, expect, it } from "vitest";
import type { MarketSearchRun, MarketSearchSource } from "@/lib/api";
import {
  describeFreshness,
  describeProvenance,
  describeSourceCounts,
  headline,
  isActive,
  refreshBlockedUntil,
  rejectionLabel,
} from "@/lib/marketSearch";

type Summary = MarketSearchRun["summary"];

function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    stage: "done",
    elapsed_s: 4.2,
    observed_at: "2026-09-30T12:00:05Z",
    comparables_recorded: 0,
    comparables_known_for_reference: 0,
    recorded_by_price_kind: {},
    price_groups: {},
    insufficient_data: false,
    insufficient_data_message: null,
    price_nature_note: null,
    recalculation: null,
    ...overrides,
  };
}

function run(overrides: Partial<MarketSearchRun> = {}): MarketSearchRun {
  return {
    id: "r1",
    opportunity_id: "o1",
    status: "succeeded",
    trigger_kind: "refresh",
    policy_version: "1.0.0",
    created_at: "2026-09-30T12:00:00Z",
    started_at: "2026-09-30T12:00:01Z",
    finished_at: "2026-09-30T12:00:05Z",
    sources: [],
    summary: summary(),
    error_code: null,
    error_message: null,
    age_minutes: 0,
    cache_ttl_hours: 6,
    stale: false,
    next_refresh_allowed_at: null,
    ...overrides,
  };
}

describe("describeFreshness", () => {
  it("dit l'âge et signale les données anciennes", () => {
    expect(describeFreshness(0, false)).toBe("Relevé à l'instant");
    expect(describeFreshness(12, false)).toBe("Relevé il y a 12 min");
    expect(describeFreshness(180, false)).toBe("Relevé il y a 3 h");
    expect(describeFreshness(500, true)).toBe(
      "Relevé il y a 8 h — données anciennes",
    );
    expect(describeFreshness(60 * 24 * 5, true)).toContain("5 jours");
    expect(describeFreshness(null, false)).toBe("");
  });
});

describe("headline", () => {
  it("n'invente aucune estimation quand les données manquent", () => {
    const text = headline(
      run({
        summary: summary({
          comparables_recorded: 1,
          comparables_known_for_reference: 1,
          insufficient_data: true,
          insufficient_data_message: "Données insuffisantes : aucune estimation.",
        }),
      }),
    );
    expect(text).toContain("Données insuffisantes");
  });

  it("distingue un échec d'une absence de résultat", () => {
    expect(headline(run({ status: "failed" }))).toContain("n'a rien pu obtenir");
    expect(headline(run())).toContain("Aucun nouveau comparable exact");
  });

  it("accorde le pluriel", () => {
    const text = headline(
      run({
        summary: summary({
          comparables_recorded: 3,
          comparables_known_for_reference: 5,
        }),
      }),
    );
    expect(text).toBe(
      "3 nouveaux comparables exacts ajoutés (5 au total pour cette référence).",
    );
  });

  it("suit l'avancement", () => {
    expect(headline(run({ status: "running" }))).toBe("Recherche en cours…");
    expect(headline(run({ status: "queued" }))).toBe("Recherche en attente…");
  });
});

describe("isActive", () => {
  it("ne poll que tant que la recherche n'est pas finie", () => {
    expect(isActive(run({ status: "running" }))).toBe(true);
    expect(isActive(run({ status: "queued" }))).toBe(true);
    for (const status of ["succeeded", "failed", "partial"] as const) {
      expect(isActive(run({ status }))).toBe(false);
    }
    expect(isActive(null)).toBe(false);
  });
});

describe("describeSourceCounts", () => {
  const base: MarketSearchSource = {
    source: "ebay",
    status: "ok",
    message: null,
    started_at: null,
    finished_at: null,
    elapsed_s: 1.2,
    complete: true,
    requests: [],
    requests_count: 2,
    read: 40,
    accepted: 3,
    recorded: 2,
    already_known: 1,
    duplicates: 1,
    fx_unavailable: 0,
    rejected: { reference_not_stated: 35, brand_not_stated: 2 },
    rejected_examples: [],
    recorded_items: [],
    informational: [],
  };

  it("compte lues, retenues et écartées", () => {
    expect(describeSourceCounts(base)).toBe(
      "40 annonces lues · 2 retenues · 37 écartées · 1 déjà connue(s) · 1 doublon(s) fusionné(s)",
    );
  });

  it("signale une lecture partielle : l'absence d'une annonce n'est alors pas une preuve", () => {
    expect(describeSourceCounts({ ...base, complete: false })).toContain(
      "lecture partielle",
    );
  });

  it("ne dit rien d'une source qui n'a rien lu à cause d'un refus", () => {
    expect(describeSourceCounts({ ...base, status: "blocked", read: 0 })).toBe("");
  });
});

describe("refreshBlockedUntil", () => {
  it("bloque l'actualisation tant que le délai minimal n'est pas passé", () => {
    const r = run({ next_refresh_allowed_at: "2026-09-30T12:15:00Z" });
    expect(refreshBlockedUntil(r, new Date("2026-09-30T12:10:00Z"))).not.toBeNull();
    expect(refreshBlockedUntil(r, new Date("2026-09-30T12:16:00Z"))).toBeNull();
    expect(refreshBlockedUntil(null)).toBeNull();
  });
});

describe("rejectionLabel", () => {
  it("traduit les motifs connus et rend les inconnus tels quels", () => {
    expect(rejectionLabel("reference_not_stated")).toContain("voisine");
    expect(rejectionLabel("motif_futur")).toBe("motif_futur");
  });
});

describe("describeProvenance", () => {
  it("garde la devise et la date d'origine, et dit ce qui est inconnu", () => {
    const lines = describeProvenance({
      source_amount: "7750",
      source_currency: "CHF",
      sold_at: "2013-05-12T00:00:00+00:00",
      fees_status: "unknown",
      configuration: {
        "métal": ["yellow gold"],
        bracelet: ["bracelet métal"],
      },
    });
    expect(lines[0]).toContain("CHF");
    expect(lines.join(" ")).toContain("2013");
    expect(lines).toContain("commission acheteur : inconnue");
    expect(lines.join(" ")).toContain("yellow gold");
  });

  it("ne dit rien d'une saisie manuelle", () => {
    expect(describeProvenance(null)).toEqual([]);
  });
});
