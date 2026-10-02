import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusDashboard } from "./status-dashboard";

describe("StatusDashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows loading then successful API and database states", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true, data: { status: "healthy" } }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            success: true,
            data: { status: "ready", database: "available" },
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<StatusDashboard />);
    expect(screen.getAllByText("Checking…")).toHaveLength(2);

    await waitFor(() => expect(screen.getAllByText("Operational")).toHaveLength(2));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows unavailable states when requests fail", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("network error")));

    render(<StatusDashboard />);

    await waitFor(() => expect(screen.getAllByText("Unavailable")).toHaveLength(2));
  });
});
