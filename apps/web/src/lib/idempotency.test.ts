import { describe, expect, it } from "vitest";
import { createKeyRegistry } from "./idempotency";

function counter(): () => string {
  let n = 0;
  return () => `cle-${++n}`;
}

describe("registre de clés d'idempotence", () => {
  it("garde la même clé tant que l'action n'a pas abouti", () => {
    const registry = createKeyRegistry(counter());

    // Le renvoi après un échec : c'est le cas que la clé existe pour couvrir.
    expect(registry.keyFor("payout")).toBe("cle-1");
    expect(registry.keyFor("payout")).toBe("cle-1");
    expect(registry.keyFor("payout")).toBe("cle-1");
  });

  it("mint une clé neuve une fois l'action aboutie", () => {
    const registry = createKeyRegistry(counter());

    expect(registry.keyFor("movement")).toBe("cle-1");
    registry.settle("movement");

    // Un second apport est un second geste, pas un renvoi du premier :
    // réemployer la clé le ferait rejeter comme un doublon.
    expect(registry.keyFor("movement")).toBe("cle-2");
  });

  it("sépare les actions distinctes", () => {
    const registry = createKeyRegistry(counter());

    expect(registry.keyFor("purchase")).toBe("cle-1");
    expect(registry.keyFor("payout")).toBe("cle-2");
    expect(registry.keyFor("purchase")).toBe("cle-1");
  });

  it("produit des clés réellement distinctes par défaut", () => {
    const registry = createKeyRegistry();
    const first = registry.keyFor("a");
    const second = registry.keyFor("b");

    expect(first).not.toBe(second);
    expect(first.length).toBeGreaterThan(8);
  });
});
