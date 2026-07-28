import type { components } from "@kairos/contracts";

export type OpportunityResponse = components["schemas"]["OpportunityResponse"];
export type OpportunityPage = components["schemas"]["OpportunityPage"];
export type CreateOpportunityRequest = components["schemas"]["CreateOpportunityRequest"];

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly code: string;
  readonly field: string | null;
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(status: number, body: {
    error: { code: string; message: string; field: string | null; details: Record<string, unknown> };
  }) {
    super(body.error.message);
    this.status = status;
    this.code = body.error.code;
    this.field = body.error.field;
    this.details = body.error.details;
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
    const body = await response.json();
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
