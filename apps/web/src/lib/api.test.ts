import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

// Le module choisit son URL de base selon la présence de `window` : sans lui,
// il se croit sur le serveur Next et va chercher `next/headers`, qui n'existe
// pas hors d'une requête. On se déclare donc côté navigateur avant de
// l'importer — c'est le chemin que ces tests décrivent.
beforeAll(() => {
  (globalThis as { window?: unknown }).window = globalThis;
});

const api = await import("./api");

function stubFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 201,
    json: async () => ({ id: "1" }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function headersOf(fetchMock: ReturnType<typeof vi.fn>): Record<string, string> {
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  return init.headers as Record<string, string>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const MOVEMENT = {
  kind: "capital_contribution" as const,
  amount: "1000.00",
  currency: "EUR",
  notes: null,
};

describe("en-tête d'idempotence", () => {
  it("part avec l'écriture quand une clé est fournie", async () => {
    const fetchMock = stubFetch();

    await api.createLedgerEntry("pf-1", MOVEMENT, {
      idempotencyKey: "cle-de-test",
    });

    expect(headersOf(fetchMock)["Idempotency-Key"]).toBe("cle-de-test");
  });

  it("reste absent quand aucune clé n'est fournie", async () => {
    const fetchMock = stubFetch();

    await api.createLedgerEntry("pf-1", MOVEMENT);

    // Absent, pas vide : l'API traite une clé vide comme une clé invalide.
    expect(headersOf(fetchMock)).not.toHaveProperty("Idempotency-Key");
  });

  it("accompagne aussi les opérations financières de l'opportunité", async () => {
    for (const call of [
      () =>
        api.recordPurchase(
          "op-1",
          { amount: "10.00", currency: "EUR", reason: "r" },
          { idempotencyKey: "k" },
        ),
      () =>
        api.recordSale(
          "op-1",
          { realized_amount: "10.00", currency: "EUR", reason: "r" },
          { idempotencyKey: "k" },
        ),
      () =>
        api.recordPayout(
          "op-1",
          { amount: null, currency: "EUR", reason: "r" },
          { idempotencyKey: "k" },
        ),
      () =>
        api.changeStatus(
          "op-1",
          { status: "buy", reason: "r" },
          { idempotencyKey: "k" },
        ),
    ]) {
      const fetchMock = stubFetch();
      await call();
      expect(headersOf(fetchMock)["Idempotency-Key"]).toBe("k");
      vi.unstubAllGlobals();
    }
  });
});
