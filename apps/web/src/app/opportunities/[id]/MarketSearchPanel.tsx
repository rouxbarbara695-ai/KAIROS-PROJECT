"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { Disclosure } from "@/components/Disclosure";
import {
  ApiError,
  getMarketSearch,
  startMarketSearch,
  type MarketSearchLatest,
  type MarketSearchSource,
} from "@/lib/api";
import { formatAmount, formatDateTime, labels } from "@/lib/labels";
import {
  describeFreshness,
  describeSourceCounts,
  headline,
  isActive,
  refreshBlockedUntil,
  rejectionLabel,
  SOURCE_STATUS_LABELS,
  sourceName,
} from "@/lib/marketSearch";
import { announceMarketChange } from "@/lib/recalculation";

const POLL_MS = 2000;

const STATUS_TONE: Record<string, string> = {
  ok: "bg-accent/15 text-accent-strong ring-accent/30",
  blocked: "bg-danger/10 text-danger ring-danger/30",
  rate_limited: "bg-amber-500/10 text-amber-500 ring-amber-500/30",
  budget_exhausted: "bg-amber-500/10 text-amber-500 ring-amber-500/30",
  error: "bg-danger/10 text-danger ring-danger/30",
  not_configured: "bg-border text-fg-muted ring-border",
};

function SourceBlock({ source }: { source: MarketSearchSource }) {
  const counts = describeSourceCounts(source);
  const rejected = Object.entries(source.rejected).sort((a, b) => b[1] - a[1]);

  return (
    <li className="rounded-md border border-border p-3" data-testid="search-source">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{sourceName(source.source)}</span>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
            STATUS_TONE[source.status] ?? STATUS_TONE.not_configured
          }`}
        >
          {SOURCE_STATUS_LABELS[source.status] ?? source.status}
        </span>
        <span className="numeric text-xs text-fg-muted">
          {source.requests_count} requête{source.requests_count > 1 ? "s" : ""}
          {source.elapsed_s ? ` · ${source.elapsed_s} s` : ""}
        </span>
      </div>

      {/* Le diagnostic exact d'un échec est affiché tel quel : il ne se
          remplace pas par « aucun résultat ». */}
      {source.message && (
        <p className="mt-1.5 text-xs text-fg-muted">{source.message}</p>
      )}
      {counts && <p className="mt-1.5 text-xs text-fg-muted">{counts}</p>}

      {(source.recorded_items.length > 0 ||
        rejected.length > 0 ||
        source.requests.length > 0) && (
        <div className="mt-2">
          <Disclosure summary="Voir le détail de cette source">
            <div className="space-y-4 text-xs">
              {source.recorded_items.length > 0 && (
                <div>
                  <p className="mb-1 font-medium text-fg">Annonces retenues</p>
                  <ul className="space-y-1">
                    {source.recorded_items.map((item) => (
                      <li key={item.comparable_id}>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-strong underline-offset-2 hover:underline"
                        >
                          {item.title}
                        </a>{" "}
                        <span className="numeric text-fg-muted">
                          — {formatAmount(item.amount, item.currency)} ·{" "}
                          {labels.priceKind(item.price_kind)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {rejected.length > 0 && (
                <div>
                  <p className="mb-1 font-medium text-fg">Annonces écartées</p>
                  <ul className="space-y-1 text-fg-muted">
                    {rejected.map(([code, count]) => (
                      <li key={code}>
                        <span className="numeric">{count}</span> ×{" "}
                        {rejectionLabel(code)}
                      </li>
                    ))}
                  </ul>
                  {source.rejected_examples.length > 0 && (
                    <ul className="mt-2 space-y-0.5 text-fg-muted">
                      {source.rejected_examples.map((example, index) => (
                        <li key={`${example.code}-${index}`}>
                          « {example.title} »
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {source.requests.length > 0 && (
                <div>
                  <p className="mb-1 font-medium text-fg">Requêtes émises</p>
                  <ul className="space-y-0.5 text-fg-muted">
                    {source.requests.map((request, index) => (
                      <li key={index}>
                        {request.label} → HTTP{" "}
                        <span className="numeric">
                          {request.http_status ?? "aucune réponse"}
                        </span>{" "}
                        <span className="numeric">({request.elapsed_s} s)</span>
                        {request.note ? ` — ${request.note}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Disclosure>
        </div>
      )}
    </li>
  );
}

export function MarketSearchPanel({
  opportunityId,
  referenceConfirmed,
}: {
  opportunityId: string;
  referenceConfirmed: boolean;
}) {
  const [state, setState] = useState<MarketSearchLatest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const wasActive = useRef(false);

  const load = useCallback(async () => {
    try {
      setState(await getMarketSearch(opportunityId));
    } catch {
      setError("Impossible de lire l'état de la recherche.");
    }
  }, [opportunityId]);

  useEffect(() => {
    void load();
    // La confirmation de la référence lance la recherche côté serveur : il faut
    // relire dès que la référence devient confirmée.
  }, [load, referenceConfirmed]);

  const run = state?.run ?? null;
  const active = isActive(run);

  // Suivre l'avancement tant que la recherche tourne, puis prévenir les autres
  // panneaux : la cote, l'analyse et les comparables viennent de changer.
  useEffect(() => {
    if (!active) {
      if (wasActive.current) {
        wasActive.current = false;
        announceMarketChange();
      }
      return;
    }
    wasActive.current = true;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [active, load]);

  function launch(force: boolean) {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      try {
        const started = await startMarketSearch(opportunityId, force);
        if (started.reused === "fresh") {
          setNotice(
            "Une recherche récente existe déjà : ses résultats sont affichés.",
          );
        } else if (started.reused === "too_soon") {
          setNotice(
            "La dernière recherche date de moins de quelques minutes : chaque requête coûte du quota à la source, elle n'a pas été relancée.",
          );
        }
        await load();
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "La recherche n'a pas pu démarrer.",
        );
      }
    });
  }

  if (!referenceConfirmed) {
    return (
      <p className="text-sm text-fg-muted">
        Confirmez la référence : KAIROS cherchera alors lui-même les annonces
        comparables. Une recherche sur une référence supposée ramènerait des
        montres qui ne sont pas la bonne.
      </p>
    );
  }

  if (state && state.configured_sources.length === 0 && !run) {
    return (
      <p className="text-sm text-fg-muted" data-testid="search-unavailable">
        La recherche automatique n&apos;est pas activée : aucune source
        n&apos;est configurée. L&apos;accès à eBay par son API officielle
        demande des identifiants (variables{" "}
        <code>EBAY_CLIENT_ID</code> et <code>EBAY_CLIENT_SECRET</code>). Tant
        qu&apos;ils manquent, la cote ne repose que sur les comparables saisis.
      </p>
    );
  }

  const blockedUntil = refreshBlockedUntil(run);
  const canSearch = (state?.configured_sources.length ?? 0) > 0;

  return (
    <div className="space-y-4" data-testid="market-search">
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-fg-muted">
          {notice}
        </p>
      )}

      {!run && state && (
        <p className="text-sm text-fg-muted">
          Aucune recherche pour cette référence.
        </p>
      )}

      {run && (
        <div className="space-y-3">
          <p className="text-sm font-medium" data-testid="search-headline">
            {headline(run)}
          </p>

          {active && (
            <div
              className="h-1.5 w-full overflow-hidden rounded-full bg-border"
              role="progressbar"
              aria-label="Recherche en cours"
            >
              <div className="h-full w-1/3 animate-pulse rounded-full bg-accent" />
            </div>
          )}

          {run.finished_at && (
            <p
              className={`text-xs ${run.stale ? "text-warning" : "text-fg-muted"}`}
              data-testid="search-freshness"
            >
              {describeFreshness(run.age_minutes, run.stale)} (
              {formatDateTime(run.finished_at)})
            </p>
          )}

          {run.error_message && (
            <p className="text-xs text-danger">{run.error_message}</p>
          )}

          {run.sources.length > 0 && (
            <ul className="space-y-2">
              {run.sources.map((source) => (
                <SourceBlock key={source.source} source={source} />
              ))}
            </ul>
          )}

          {run.status !== "queued" && run.status !== "running" && (
            <>
              {/* La nature des prix est dite à côté du résultat : ce sont des
                  annonces observées, jamais des ventes conclues. */}
              {run.summary.price_nature_note && (
                <p className="text-xs text-fg-muted">
                  {run.summary.price_nature_note}
                </p>
              )}
              {run.summary.recalculation?.status === "recalculated" && (
                <p className="text-xs text-fg-muted">
                  La cote et l&apos;analyse ont été recalculées automatiquement.
                </p>
              )}
              {run.summary.recalculation?.status === "valuation_only" && (
                <p className="text-xs text-fg-muted">
                  La cote a été recalculée ; l&apos;analyse n&apos;a pas pu
                  l&apos;être
                  {run.summary.recalculation.detail
                    ? ` : ${run.summary.recalculation.detail}`
                    : "."}
                </p>
              )}
            </>
          )}
        </div>
      )}

      {canSearch && !active && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => launch(Boolean(run))}
            disabled={isPending || blockedUntil !== null}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {run ? "Actualiser" : "Lancer la recherche"}
          </button>
          {blockedUntil && (
            <span className="text-xs text-fg-muted">
              Actualisation possible à partir de{" "}
              {formatDateTime(blockedUntil.toISOString())}.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
