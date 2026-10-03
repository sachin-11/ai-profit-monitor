import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventCost } from "@/lib/projects-api";
import { EventCostCell } from "./event-cost-cell";

const calculated: EventCost = {
  id: "cost-1", model_price_id: "price-1", status: "calculated", currency: "USD",
  uncached_input_tokens: 1, cached_input_tokens: 0, regular_output_tokens: 0, reasoning_tokens: 0,
  uncached_input_cost: "0.000000000000000001", cached_input_cost: "0.000000000000000000",
  output_cost: "0.000000000000000000", reasoning_cost: "0.000000000000000000",
  total_cost: "0.000000000000000001", reason_code: null, reason_detail: null,
  calculation_version: "text_tokens_v1", calculated_at: "2026-10-03T12:00:00Z",
  model_price: { catalog_version: "test-v1", source_name: "Synthetic fixture", reasoning_billing_mode: "included_in_output" },
};

describe("EventCostCell", () => {
  it("keeps tiny amounts exact and shows their price provenance", () => {
    render(<EventCostCell cost={calculated} />);
    expect(screen.getAllByText("USD 0.000000000000000001")).toHaveLength(2);
    expect(screen.getByText("Cost breakdown")).toBeInTheDocument();
    expect(screen.getByText("Price record: price-1")).toBeInTheDocument();
    expect(screen.getByText("Source: Synthetic fixture")).toBeInTheDocument();
  });

  it.each(["unpriced", "unsupported", "invalid"] as const)("never renders %s as zero", (status) => {
    render(<EventCostCell cost={{ ...calculated, status, total_cost: null, reason_detail: "No supported price" }} />);
    expect(screen.getByText(status)).toBeInTheDocument();
    expect(screen.getByText("No supported price")).toBeInTheDocument();
    expect(screen.queryByText(/USD/)).not.toBeInTheDocument();
  });

  it("shows a calculated zero distinctly from a missing calculation", () => {
    const { rerender } = render(<EventCostCell cost={{ ...calculated, total_cost: "0.000000000000000000" }} />);
    expect(screen.getAllByText("USD 0").length).toBeGreaterThan(0);
    rerender(<EventCostCell cost={null} />);
    expect(screen.getByText("Not calculated")).toBeInTheDocument();
    expect(screen.queryByText("USD 0")).not.toBeInTheDocument();
  });
});
