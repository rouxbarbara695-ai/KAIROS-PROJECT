import type { components } from "@kairos/contracts";

export type OpportunityResponse = components["schemas"]["OpportunityResponse"];
export type OpportunityPage = components["schemas"]["OpportunityPage"];
export type CreateOpportunityRequest = components["schemas"]["CreateOpportunityRequest"];
export type AuditEventResponse = components["schemas"]["AuditEventResponse"];
export type AuditEventPage = components["schemas"]["AuditEventPage"];
export type PriceInputCreate = components["schemas"]["PriceInputCreate"];

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    field?: string | null;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  readonly code: string;
  readonly field: string | null;
  readonly details: Record<string, unknown>;
  readonly status: number;

  /**
   * Toutes les réponses d'erreur ne suivent pas le catalogue : un 404 de
   * routage ou une panne d'infrastructure renvoient une autre forme. Sans
   * garde, la lecture du corps échouerait et masquerait l'erreur réelle
   * derrière un `TypeError`.
   */
  constructor(status: number, body: unknown) {
    const envelope = (body ?? {}) as ErrorEnvelope;
    const error = envelope.error;
    super(error?.message ?? `Erreur ${status}.`);
    this.status = status;
    this.code = error?.code ?? "UNKNOWN_ERROR";
    this.field = error?.field ?? null;
    this.details = error?.details ?? {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    // Un corps illisible (page HTML, réponse vide) ne doit pas éclipser le
    // statut, qui reste l'information la plus fiable.
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function getMe(): Promise<{ user_id: string; portfolio_ids: string[] }> {
  return request("/me");
}

export function listOpportunities(params?: {
  status?: string;
  brand?: string;
  reference?: string;
  cursor?: string;
}): Promise<OpportunityPage> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.brand) query.set("brand", params.brand);
  if (params?.reference) query.set("reference", params.reference);
  if (params?.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<OpportunityPage>(`/opportunities${suffix}`);
}

export function getOpportunity(id: string): Promise<OpportunityResponse> {
  return request<OpportunityResponse>(`/opportunities/${id}`);
}

export function createOpportunity(
  body: CreateOpportunityRequest,
): Promise<OpportunityResponse> {
  return request<OpportunityResponse>("/opportunities", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function confirmReference(
  opportunityId: string,
  body: { status: string; reference_id?: string; reason: string },
): Promise<OpportunityResponse> {
  return request<OpportunityResponse>(
    `/opportunities/${opportunityId}/reference-confirmations`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function patchWatchProfile(
  opportunityId: string,
  body: Record<string, unknown>,
): Promise<OpportunityResponse> {
  return request<OpportunityResponse>(
    `/opportunities/${opportunityId}/watch-profile`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function patchSellerProfile(
  opportunityId: string,
  body: Record<string, unknown>,
): Promise<OpportunityResponse> {
  return request<OpportunityResponse>(
    `/opportunities/${opportunityId}/seller-profile`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function listOpportunityEvents(
  opportunityId: string,
  params?: { cursor?: string },
): Promise<AuditEventPage> {
  const query = new URLSearchParams();
  if (params?.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AuditEventPage>(
    `/opportunities/${opportunityId}/events${suffix}`,
  );
}

export function addPriceInput(
  opportunityId: string,
  body: PriceInputCreate,
): Promise<{ id: string }> {
  return request<{ id: string }>(
    `/opportunities/${opportunityId}/price-inputs`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type ComparableResponse = components["schemas"]["ComparableResponse"];
export type ComparablePage = components["schemas"]["ComparablePage"];
export type ComparableCreate = components["schemas"]["ComparableCreate"];
export type ComparableImportResult =
  components["schemas"]["ComparableImportResult"];
export type ValuationResponse = components["schemas"]["ValuationResponse"];

export function listComparables(
  opportunityId: string,
): Promise<ComparablePage> {
  return request<ComparablePage>(
    `/opportunities/${opportunityId}/comparables?limit=100`,
  );
}

export function createComparable(
  opportunityId: string,
  body: ComparableCreate,
): Promise<ComparableResponse> {
  return request<ComparableResponse>(
    `/opportunities/${opportunityId}/comparables`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function importComparables(
  opportunityId: string,
  content: string,
): Promise<ComparableImportResult> {
  return request<ComparableImportResult>(
    `/opportunities/${opportunityId}/comparables/import`,
    { method: "POST", body: JSON.stringify({ content }) },
  );
}

export function createOverride(
  comparableId: string,
  body: {
    excluded: boolean;
    exclusion_reason?: string;
    reason: string;
  },
): Promise<unknown> {
  return request(`/comparables/${comparableId}/overrides`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Dernière cote, ou `null` s'il n'y en a aucune.
 *
 * L'absence de cote est l'état initial de tout dossier : la traiter comme
 * une erreur ferait clignoter un échec à l'ouverture de chaque fiche.
 */
export async function getLatestValuation(
  opportunityId: string,
): Promise<ValuationResponse | null> {
  try {
    return await request<ValuationResponse>(
      `/opportunities/${opportunityId}/valuations/latest`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export function createValuation(
  opportunityId: string,
): Promise<ValuationResponse> {
  return request<ValuationResponse>(
    `/opportunities/${opportunityId}/valuations`,
    { method: "POST" },
  );
}

export type AnalysisResponse = components["schemas"]["AnalysisResponse"];

export function createAnalysis(
  opportunityId: string,
): Promise<AnalysisResponse> {
  return request<AnalysisResponse>(`/opportunities/${opportunityId}/analyses`, {
    method: "POST",
  });
}

/**
 * Dernière analyse, ou `null` s'il n'y en a aucune.
 *
 * L'absence d'analyse est l'état initial de tout dossier, pas une erreur :
 * la traiter comme telle ferait clignoter un message d'échec à l'ouverture
 * de chaque fiche.
 */
export async function getLatestAnalysis(
  opportunityId: string,
): Promise<AnalysisResponse | null> {
  try {
    return await request<AnalysisResponse>(
      `/opportunities/${opportunityId}/analyses/latest`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export type PortfolioOverview =
  components["schemas"]["PortfolioOverviewResponse"];
export type LedgerMovementCreate =
  components["schemas"]["LedgerMovementCreate"];
export type LedgerMovementResponse =
  components["schemas"]["LedgerMovementResponse"];

export function getPortfolioOverview(
  portfolioId: string,
): Promise<PortfolioOverview> {
  return request<PortfolioOverview>(`/portfolios/${portfolioId}/overview`);
}

export function createLedgerEntry(
  portfolioId: string,
  body: LedgerMovementCreate,
): Promise<LedgerMovementResponse> {
  return request<LedgerMovementResponse>(
    `/portfolios/${portfolioId}/ledger-entries`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type PlatformResponse = components["schemas"]["PlatformResponse"];
export type PlatformRuleCreate = components["schemas"]["PlatformRuleCreate"];

export function listPlatforms(): Promise<PlatformResponse[]> {
  return request<PlatformResponse[]>("/platforms");
}

export function createPlatformRule(
  code: string,
  body: PlatformRuleCreate,
): Promise<unknown> {
  return request(`/platforms/${code}/rules`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type StrategyResponse = components["schemas"]["StrategyResponse"];
export type StrategyUpdate = components["schemas"]["StrategyUpdate"];

export function getStrategy(portfolioId: string): Promise<StrategyResponse> {
  return request<StrategyResponse>(`/portfolios/${portfolioId}/strategy`);
}

export function updateStrategy(
  portfolioId: string,
  body: StrategyUpdate,
): Promise<StrategyResponse> {
  return request<StrategyResponse>(`/portfolios/${portfolioId}/strategy`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type PurchaseCreate = components["schemas"]["PurchaseCreate"];
export type StatusChangeRequest =
  components["schemas"]["StatusChangeRequest"];

export function recordPurchase(
  opportunityId: string,
  body: PurchaseCreate,
): Promise<{ id: string; amount_eur: string; purchased_at: string }> {
  return request(`/opportunities/${opportunityId}/purchase`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function changeStatus(
  opportunityId: string,
  body: StatusChangeRequest,
): Promise<unknown> {
  return request(`/opportunities/${opportunityId}/status`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type SaleListingCreate = components["schemas"]["SaleListingCreate"];
export type SaleCreate = components["schemas"]["SaleCreate"];
export type PayoutCreate = components["schemas"]["PayoutCreate"];

export function recordSaleListing(
  opportunityId: string,
  body: SaleListingCreate,
): Promise<unknown> {
  return request(`/opportunities/${opportunityId}/sale-listing`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function recordSale(
  opportunityId: string,
  body: SaleCreate,
): Promise<unknown> {
  return request(`/opportunities/${opportunityId}/sale`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function recordPayout(
  opportunityId: string,
  body: PayoutCreate,
): Promise<unknown> {
  return request(`/opportunities/${opportunityId}/payout`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
