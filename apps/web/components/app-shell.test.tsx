import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./app-shell";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const meResponse = {
  success: true,
  data: {
    user: {
      id: "user-1",
      email: "owner@example.com",
      display_name: "Owner User",
      is_active: true,
      created_at: "2026-10-03T00:00:00Z",
    },
    memberships: [
      {
        id: "membership-1",
        role: "owner",
        created_at: "2026-10-03T00:00:00Z",
        organization: {
          id: "org-1",
          name: "Acme AI",
          slug: "acme-ai",
          created_at: "2026-10-03T00:00:00Z",
          updated_at: "2026-10-03T00:00:00Z",
        },
      },
    ],
  },
};

describe("AppShell", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it("renders the protected profile and organization state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify(meResponse), { status: 200 }),
      ),
    );
    render(<AppShell />);

    expect(screen.getByText("Loading workspace…")).toBeInTheDocument();
    expect(await screen.findByText("Owner User")).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("Acme AI")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
  });

  it("redirects unauthenticated users", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("unauthorized")));
    render(<AppShell />);

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
  });

  it("logs out without storing a session token in browser storage", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(meResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true, data: { logged_out: true } }), {
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<AppShell />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "http://localhost:8000/api/v1/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(storageSpy).not.toHaveBeenCalled();
  });
});
