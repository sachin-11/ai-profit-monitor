import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "./projects-page";
import { ProjectDetail } from "./project-detail";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const project = {
  id: "project-1",
  organization_id: "org-1",
  name: "Chat Backend",
  slug: "chat-backend",
  environment: "production",
  description: "Metadata only",
  is_active: true,
  created_at: "2026-10-03T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
};

function profile(role: "owner" | "member") {
  return {
    success: true,
    data: {
      user: { id: "user-1", email: "user@example.com", display_name: "User", is_active: true, created_at: "2026-10-03T00:00:00Z" },
      memberships: [{ id: "membership-1", role, created_at: "2026-10-03T00:00:00Z", organization: { id: "org-1", name: "Acme AI", slug: "acme-ai", created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z" } }],
    },
  };
}

describe("ProjectsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("shows loading and an empty state for an owner", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return new Response(JSON.stringify(profile("owner")));
      return new Response(JSON.stringify({ success: true, data: { projects: [], role: "owner" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProjectsPage />);

    expect(screen.getByText("Loading projects…")).toBeInTheDocument();
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create project" })).toBeInTheDocument();
  });

  it("shows member projects without creation controls", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockImplementation(async (input) => {
      if (String(input).endsWith("/auth/me")) return new Response(JSON.stringify(profile("member")));
      return new Response(JSON.stringify({ success: true, data: { projects: [project], role: "member" } }));
    }));
    render(<ProjectsPage />);

    expect(await screen.findByText("Chat Backend")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create project" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Chat Backend/ })).toHaveAttribute("href", "/app/projects/project-1");
  });

  it("creates a project and shows it in the list", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return new Response(JSON.stringify(profile("owner")));
      if (init?.method === "POST") return new Response(JSON.stringify({ success: true, data: { project, role: "owner" } }), { status: 201 });
      return new Response(JSON.stringify({ success: true, data: { projects: [], role: "owner" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProjectsPage />);
    await screen.findByText("No projects yet.");
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Chat Backend" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Chat Backend")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/organizations/org-1/projects",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});

describe("ProjectDetail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("shows a clear not-found state for inaccessible projects", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ success: false, error: { code: "not_found", message: "Project not found" } }), { status: 404 }),
    ));
    render(<ProjectDetail projectId="another-tenant-project" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found or access unavailable.");
  });

  it("hides key-management controls from members and uses a placeholder example", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockImplementation(async (input) => {
      if (String(input).includes("/events")) return new Response(JSON.stringify({ success: true, data: { events: [], next_cursor: null } }));
      return new Response(JSON.stringify({ success: true, data: { project, role: "member" } }));
    }));
    render(<ProjectDetail projectId="project-1" />);
    await waitFor(() => expect(screen.getByText("Chat Backend")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Create key" })).not.toBeInTheDocument();
    expect(screen.getByText(/Authorization: Bearer YOUR_PROJECT_API_KEY/)).toBeInTheDocument();
  });
});
