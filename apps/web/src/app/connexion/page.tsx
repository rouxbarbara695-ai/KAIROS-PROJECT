"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError, login } from "@/lib/api";

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent";

export default function LoginPage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    startTransition(async () => {
      try {
        await login(String(data.get("email")), String(data.get("password")));
        // `refresh()` en plus de `push()` : les pages sont rendues côté
        // serveur et ont été mises en cache sans session. Sans invalidation,
        // l'utilisateur reviendrait sur une page « non connecté ».
        router.refresh();
        router.push("/");
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "La connexion a échoué. Réessayez.",
        );
      }
    });
  }

  return (
    <div className="mx-auto max-w-sm space-y-6 py-16">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">KAIROS</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Connectez-vous pour accéder à votre portefeuille.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">Adresse</span>
          <input
            name="email"
            type="email"
            autoComplete="username"
            required
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-fg-muted">Mot de passe</span>
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className={inputClass}
          />
        </label>

        {error && <p className="text-sm text-danger">{error}</p>}

        <button
          type="submit"
          disabled={isPending}
          className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-bg disabled:opacity-50"
        >
          {isPending ? "Connexion…" : "Se connecter"}
        </button>
      </form>

      <p className="text-xs text-fg-muted">
        Les comptes se créent en ligne de commande sur la machine qui héberge la
        base. Il n&apos;y a pas d&apos;inscription : KAIROS ne sert qu&apos;un
        portefeuille.
      </p>
    </div>
  );
}
