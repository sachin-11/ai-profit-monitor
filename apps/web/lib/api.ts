export interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export interface HealthData {
  status: "healthy";
}

export interface ReadinessData {
  status: "ready" | "not_ready";
  database: "available" | "unavailable";
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return (await response.json()) as ApiResponse<T>;
}

export const api = {
  health: () => request<HealthData>("/health"),
  readiness: () => request<ReadinessData>("/ready"),
};

