import { MembershipRole, request } from "@/lib/api";

export type ProjectEnvironment = "development" | "staging" | "production";
export type EventStatus = "success" | "error" | "timeout" | "cancelled";

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  environment: ProjectEnvironment;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectApiKey {
  id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface UsageEvent {
  id: string;
  project_id: string;
  organization_id: string;
  client_event_id: string;
  occurred_at: string;
  provider: string;
  model: string;
  feature: string;
  customer_external_id: string | null;
  status: EventStatus;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number | null;
}

export interface EventFilters {
  provider?: string;
  feature?: string;
  status?: EventStatus | "";
}

export const projectsApi = {
  list: (organizationId: string) =>
    request<{ projects: Project[]; role: MembershipRole }>(
      `/api/v1/organizations/${organizationId}/projects`,
    ),
  create: (
    organizationId: string,
    input: { name: string; environment: ProjectEnvironment; description?: string },
  ) =>
    request<{ project: Project; role: MembershipRole }>(
      `/api/v1/organizations/${organizationId}/projects`,
      { method: "POST", body: JSON.stringify(input) },
    ),
  get: (projectId: string) =>
    request<{ project: Project; role: MembershipRole }>(`/api/v1/projects/${projectId}`),
  keys: (projectId: string) =>
    request<{ api_keys: ProjectApiKey[] }>(`/api/v1/projects/${projectId}/api-keys`),
  createKey: (projectId: string, input: { name: string; expires_at?: string | null }) =>
    request<{ api_key: ProjectApiKey; raw_key: string; message: string }>(
      `/api/v1/projects/${projectId}/api-keys`,
      { method: "POST", body: JSON.stringify(input) },
    ),
  revokeKey: (projectId: string, keyId: string) =>
    request<{ api_key: ProjectApiKey }>(
      `/api/v1/projects/${projectId}/api-keys/${keyId}/revoke`,
      { method: "POST" },
    ),
  events: (projectId: string, filters: EventFilters = {}, cursor?: string) => {
    const query = new URLSearchParams({ limit: "10" });
    if (filters.provider) query.set("provider", filters.provider);
    if (filters.feature) query.set("feature", filters.feature);
    if (filters.status) query.set("status", filters.status);
    if (cursor) query.set("cursor", cursor);
    return request<{ events: UsageEvent[]; next_cursor: string | null }>(
      `/api/v1/projects/${projectId}/events?${query.toString()}`,
    );
  },
};
