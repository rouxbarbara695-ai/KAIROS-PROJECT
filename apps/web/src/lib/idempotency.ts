"use client";

import { useCallback, useRef } from "react";

/**
 * Clés d'idempotence côté navigateur.
 *
 * La règle tient en une phrase : **une nouvelle action reçoit une clé neuve,
 * un renvoi de la même action garde la sienne.** C'est le renvoi qui compte —
 * double clic, bouton réappuyé après une coupure réseau, formulaire resoumis
 * parce que rien ne s'est affiché. Sans clé stable, chacun de ces gestes crée
 * une seconde écriture financière que rien ne permet ensuite de distinguer
 * d'un doublon volontaire.
 *
 * La clé n'est oubliée qu'une fois l'action **aboutie**. Un échec la conserve
 * délibérément : c'est précisément le cas où l'utilisateur va réessayer, et le
 * seul moment où l'on ignore si l'appel précédent a écrit ou non.
 *
 * La politique est écrite en fonction ordinaire, hors de React : c'est elle
 * qui porte la garantie, et elle se vérifie sans monter de composant.
 */
export function newIdempotencyKey(): string {
  // `randomUUID` n'existe qu'en contexte sécurisé (HTTPS ou localhost). En
  // clair, une clé de moindre qualité vaut mieux qu'aucune protection :
  // l'unicité ne joue qu'entre les envois d'un même utilisateur.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export type ActionKeys = {
  /** Clé de cette action : celle déjà en cours si elle existe, sinon une neuve. */
  keyFor: (action: string) => string;
  /** L'action a abouti : la prochaine du même nom sera une action différente. */
  settle: (action: string) => void;
};

export function createKeyRegistry(
  mint: () => string = newIdempotencyKey,
): ActionKeys {
  const keys = new Map<string, string>();

  return {
    keyFor(action: string): string {
      const existing = keys.get(action);
      if (existing !== undefined) return existing;
      const minted = mint();
      keys.set(action, minted);
      return minted;
    },
    settle(action: string): void {
      keys.delete(action);
    },
  };
}

/**
 * Le registre d'un composant.
 *
 * Il vit dans une `ref` : il survit aux rendus mais pas au rechargement de la
 * page. C'est suffisant — après un rechargement complet, l'utilisateur voit
 * l'état réel et ne renvoie plus à l'aveugle.
 */
export function useActionKeys(): ActionKeys {
  const registry = useRef<ActionKeys | null>(null);
  registry.current ??= createKeyRegistry();

  const keyFor = useCallback(
    (action: string) => registry.current!.keyFor(action),
    [],
  );
  const settle = useCallback(
    (action: string) => registry.current!.settle(action),
    [],
  );

  return { keyFor, settle };
}
