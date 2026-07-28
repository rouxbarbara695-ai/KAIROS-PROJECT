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
