import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

beforeAll(() => {
  (globalThis as { window?: unknown }).window = globalThis;
});

const api = await import("./api");

function stubJson(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () => ({
    ok: status < 400,
    status,
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const REFUSED = {
  url: "https://www.chrono24.fr/rolex/x--id1.htm",
  platform_code: "chrono24",
  access_mode: "assisted",
  succeeded: false,
  fields: {},
  photos: [],
  warnings: [],
  failure: {
    code: "COLLECTOR_NOT_AUTHORIZED",
    message: "Chrono24 protège ses pages contre les accès automatisés.",
    details: { reason: "protected_by_platform", fallback: "assisted_import" },
  },
};

describe("récupération d'une annonce", () => {
  it("n'est pas traitée comme une panne quand la plateforme refuse", async () => {
    // L'API rend `200` avec `succeeded: false` : c'est un résultat, pas une
    // erreur. Le client doit le rendre tel quel, sinon l'interface affiche un
    // échec générique là où elle devrait proposer l'import assisté.
    stubJson(REFUSED);

    const result = await api.prefillListing(
      "https://www.chrono24.fr/rolex/x--id1.htm",
    );

    expect(result.succeeded).toBe(false);
    expect(result.failure?.details?.fallback).toBe("assisted_import");
    // Le lien revient dans la réponse : le formulaire n'a rien à recoller.
    expect(result.url).toContain("chrono24.fr");
  });

  it("envoie le contenu collé sans jamais joindre la plateforme", async () => {
    const fetchMock = stubJson({ ...REFUSED, succeeded: true });

    await api.prefillListingFromContent(
      "https://www.chrono24.fr/rolex/x--id1.htm",
      "<html>…</html>",
    );

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toContain("/listings/prefill/assisted");
    expect(JSON.parse(String(init.body))).toMatchObject({
      url: "https://www.chrono24.fr/rolex/x--id1.htm",
      content: "<html>…</html>",
    });
  });

  it("demande le mode d'accès avec une URL échappée", async () => {
    const fetchMock = stubJson({
      platform_code: "ebay",
      access_mode: "forbidden",
      explanation: "…",
    });

    await api.platformAccess("https://www.ebay.fr/itm/1?a=b&c=d");

    const [path] = fetchMock.mock.calls[0] as [string];
    // Sans échappement, `&c=d` deviendrait un second paramètre de requête.
    expect(path).toContain(
      "url=https%3A%2F%2Fwww.ebay.fr%2Fitm%2F1%3Fa%3Db%26c%3Dd",
    );
  });
});
