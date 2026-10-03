export interface ApiResponse<T> {
  success: true;
  data: T;
}

interface ErrorResponse {
  success: false;
  error: { code: string; message: string };
}

export interface HealthData {
  status: "healthy";
}

export interface ReadinessData {
  status: "ready" | "not_ready";
  database: "available" | "unavailable";
}

export type MembershipRole = "owner" | "admin" | "member";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface Membership {
  id: string;
  role: MembershipRole;
  created_at: string;
  organization: Organization;
}

export interface MeData {
  user: User;
  memberships: Membership[];
}

export interface RegisterInput {
  display_name: string;
  email: string;
  password: string;
  organization_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  const payload = (await response.json()) as ApiResponse<T> | ErrorResponse;
  if (!response.ok || !payload.success) {
    const error = !payload.success ? payload.error : undefined;
    throw new ApiError(
      error?.message ?? "Request failed",
      error?.code ?? "request_failed",
      response.status,
    );
  }
  return payload;
}

export const api = {
  health: () => request<HealthData>("/health"),
  readiness: () => request<ReadinessData>("/ready"),
  auth: {
    register: (input: RegisterInput) =>
      request<{ user: User; organization: Organization; membership: Membership }>(
        "/api/v1/auth/register",
        { method: "POST", body: JSON.stringify(input) },
      ),
    login: (input: LoginInput) =>
      request<{ user: User }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    logout: () => request<{ logged_out: boolean }>("/api/v1/auth/logout", { method: "POST" }),
    me: () => request<MeData>("/api/v1/auth/me"),
  },
};

