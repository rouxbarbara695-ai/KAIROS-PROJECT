"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { logout } from "@/lib/api";

export function LogoutButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          // Même si la révocation échoue, on renvoie vers la connexion :
          // rester sur un écran authentifié après un clic sur « déconnexion »
          // serait pire que le doute.
          await logout().catch(() => undefined);
          router.refresh();
          router.push("/connexion");
        })
      }
      className="transition-colors hover:text-fg disabled:opacity-50"
    >
      Déconnexion
    </button>
  );
}
