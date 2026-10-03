import { EventCost } from "@/lib/projects-api";

// Monetary strings remain strings: even the smallest stored amount stays visible.
export function displayDecimal(value: string): string {
  return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}

export function EventCostCell({ cost }: { cost?: EventCost | null }) {
  if (!cost) return <span className="text-ink/60">Not calculated</span>;
  if (cost.status !== "calculated" || cost.total_cost === null) {
    return <div className="max-w-xs py-3">
      <span className="font-medium capitalize text-amber-800">{cost.status}</span>
      <p className="mt-1 text-xs text-ink/60">{cost.reason_detail ?? "Cost is unavailable."}</p>
    </div>;
  }
  const components = [
    ["Uncached input", cost.uncached_input_tokens, cost.uncached_input_cost],
    ["Cached input", cost.cached_input_tokens, cost.cached_input_cost],
    ["Regular output", cost.regular_output_tokens, cost.output_cost],
    ["Reasoning", cost.reasoning_tokens, cost.reasoning_cost],
  ] as const;
  return <div className="min-w-48 py-3">
    <span className="font-medium tabular-nums">{cost.currency} {displayDecimal(cost.total_cost)}</span>
    <details className="mt-1 text-xs text-ink/65">
      <summary className="cursor-pointer">Cost breakdown</summary>
      <dl className="mt-2 space-y-2">
        {components.map(([label, tokens, amount]) => <div key={label}>
          <dt>{label} ({tokens.toLocaleString()} tokens)</dt>
          <dd className="tabular-nums">{cost.currency} {amount === null ? "Unavailable" : displayDecimal(amount)}</dd>
        </div>)}
      </dl>
      <p className="mt-3">Source: {cost.model_price?.source_name}</p>
      <p>Catalog: {cost.model_price?.catalog_version}</p>
      <p>Reasoning: {cost.model_price?.reasoning_billing_mode.replaceAll("_", " ")}</p>
      <p className="mt-2 break-all">Price record: {cost.model_price_id}</p>
      <p>Calculation: {cost.calculation_version}</p>
      <p>{new Date(cost.calculated_at).toLocaleString()}</p>
    </details>
  </div>;
}
