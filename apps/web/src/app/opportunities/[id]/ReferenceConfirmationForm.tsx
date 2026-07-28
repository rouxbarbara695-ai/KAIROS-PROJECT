"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { confirmReference } from "@/lib/api";

export function ReferenceConfirmationForm({
  opportunityId,
  currentStatus,
  referenceId,
}: {
  opportunityId: string;
  currentStatus: string;
  referenceId: string | null;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  if (currentStatus === "confirmed" || currentStatus === "corrected") {
    return (
      <p className="text-sm text-fg-muted">
        Référence déjà confirmée. Une nouvelle confirmation peut être ajoutée
        via l&rsquo;API si nécessaire.
      </p>
    );
  }

  function submit(status: "confirmed" | "unknown") {
    if (!reason.trim()) {
      setError("Un motif est requis.");
      return;
    }
    if (status === "confirmed" && !referenceId) {
      setError("Aucune référence à confirmer.");
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        await confirmReference(opportunityId, {
          status,
          reason,
          ...(status === "confirmed" ? { reference_id: referenceId! } : {}),
        });
        router.refresh();
        setReason("");
      } catch {
        setError("La confirmation a échoué.");
      }
    });
  }

  return (
    <div className="space-y-3">
      <input
        type="text"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Motif (ex. référence visible sur les papiers)"
        className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => submit("confirmed")}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
        >
          Confirmer
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => submit("unknown")}
          className="rounded-md border border-border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Marquer inconnue
        </button>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
