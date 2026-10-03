import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiKeysSection } from "./api-keys-section";
import { RecentEvents } from "./recent-events";

const key = {
  id: "key-1",
  project_id: "project-1",
  name: "Backend integration",
  key_prefix: "0123456789abcdef",
  created_at: "2026-10-03T00:00:00Z",
  last_used_at: null,
  expires_at: null,
  revoked_at: null,
};

const rawKey = "aipm_production_0123456789abcdef_aVerySecretKeyThatShouldBeShownOnlyOnce123";

describe("ApiKeysSection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the new raw key once and never stores it in browser storage", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (_input, init) => {
      if (init?.method === "POST") return new Response(JSON.stringify({ success: true, data: { api_key: key, raw_key: rawKey, message: "Copy now" } }), { status: 201 });
      return new Response(JSON.stringify({ success: true, data: { api_keys: [] } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<ApiKeysSection projectId="project-1" />);
    await screen.findByText("No API keys yet.");
    fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "Backend integration" } });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));

    expect(await screen.findByText(rawKey)).toBeInTheDocument();
    expect(screen.getByText(/cannot be retrieved later/)).toBeInTheDocument();
    expect(storageSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(rawKey)).not.toBeInTheDocument();
    expect(screen.getByText("Prefix 0123456789abcdef", { exact: false })).toBeInTheDocument();
  });

  it("confirms revocation and updates the key state", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (_input, init) => {
      if (init?.method === "POST") return new Response(JSON.stringify({ success: true, data: { api_key: { ...key, revoked_at: "2026-10-03T12:00:00Z" } } }));
      return new Response(JSON.stringify({ success: true, data: { api_keys: [key] } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ApiKeysSection projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.getByText("Revoked")).toBeInTheDocument());
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/projects/project-1/api-keys/key-1/revoke",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});

describe("RecentEvents", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows loading, empty and error states", async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn<typeof fetch>().mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<RecentEvents projectId="project-1" />);
    expect(screen.getByText("Loading events…")).toBeInTheDocument();
    resolveFirst?.(new Response(JSON.stringify({ success: true, data: { events: [], next_cursor: null } })));
    expect(await screen.findByText("No events found.")).toBeInTheDocument();
    fetchMock.mockRejectedValueOnce(new Error("network unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("network unavailable");
  });

  it("shows populated metadata and advances to the next cursor", async () => {
    const first = { id: "event-1", occurred_at: "2026-10-03T00:00:00Z", provider: "openai", model: "gpt-4o-mini", feature: "assistant", customer_external_id: "customer-123", status: "success", input_tokens: 42, output_tokens: 12, duration_ms: 350 };
    const second = { ...first, id: "event-2", provider: "anthropic" };
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, data: { events: [first], next_cursor: "cursor-2" } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, data: { events: [second], next_cursor: null } })));
    vi.stubGlobal("fetch", fetchMock);
    render(<RecentEvents projectId="project-1" />);
    expect(await screen.findByText("gpt-4o-mini")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(screen.getByText("anthropic")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("cursor=cursor-2"),
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
