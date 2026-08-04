"use client";

import { useEffect } from "react";
import Link from "next/link";

/**
 * Frontière d'erreur (POL-003).
 *
 * Sans elle, une erreur serveur affichait la trace brute de Next.js — au
 * milieu d'une négociation, ce n'est pas une information, c'est un écran de
 * débogage. Le détail reste dans la console, où il sert à qui le cherche.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const expired = error.message.toLowerCase().includes("session");

  return (
    <div className="mx-auto max-w-md space-y-4 py-16">
      <h1 className="text-xl font-semibold">
        {expired ? "Session expirée" : "Quelque chose n'a pas fonctionné"}
      </h1>
      <p className="text-sm text-fg-muted">
        {expired
          ? "Reconnectez-vous pour reprendre où vous en étiez."
          : "L'opération n'a pas abouti. Rien n'a été enregistré à moitié : le registre et les analyses ne se modifient jamais partiellement."}
      </p>
      <div className="flex gap-3">
        {expired ? (
          <Link
            href="/connexion"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg"
          >
            Se reconnecter
          </Link>
        ) : (
          <button
            type="button"
            onClick={reset}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg"
          >
            Réessayer
          </button>
        )}
        <Link
          href="/opportunities"
          className="rounded-md border border-border px-3 py-1.5 text-sm"
        >
          Retour aux opportunités
        </Link>
      </div>
    </div>
  );
}
