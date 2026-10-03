"use client";

import { FormEvent, useEffect, useState } from "react";

import { EventFilters, EventStatus, UsageEvent, projectsApi } from "@/lib/projects-api";
import { EventCostCell } from "@/components/event-cost-cell";

export function RecentEvents({ projectId }: { projectId: string }) {
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [filters, setFilters] = useState<EventFilters>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    projectsApi.events(projectId).then((result) => {
      if (!active) return;
      setEvents(result.data.events);
      setNextCursor(result.data.next_cursor);
    }).catch(() => {
      if (active) setError("Could not load recent events.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [projectId]);

  async function load(nextFilters: EventFilters, cursor?: string) {
    setLoading(true);
    setError("");
    try {
      const result = await projectsApi.events(projectId, nextFilters, cursor);
      setEvents(result.data.events);
      setNextCursor(result.data.next_cursor);
      setFilters(nextFilters);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load recent events.");
    } finally {
      setLoading(false);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void load({
      provider: String(form.get("provider") ?? "").trim(),
      feature: String(form.get("feature") ?? "").trim(),
      status: String(form.get("status") ?? "") as EventStatus | "",
    });
  }

  return (
    <section className="rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card" aria-label="Recent events">
      <h2 className="text-2xl font-semibold">Recent events</h2>
      <form onSubmit={applyFilters} className="mt-5 flex flex-wrap items-end gap-3">
        <label className="text-sm font-medium">Provider<input name="provider" maxLength={40} className="mt-2 block rounded-xl border border-ink/15 px-3 py-2" /></label>
        <label className="text-sm font-medium">Feature<input name="feature" maxLength={100} className="mt-2 block rounded-xl border border-ink/15 px-3 py-2" /></label>
        <label className="text-sm font-medium">Status<select name="status" className="mt-2 block rounded-xl border border-ink/15 px-3 py-2"><option value="">All</option><option value="success">Success</option><option value="error">Error</option><option value="timeout">Timeout</option><option value="cancelled">Cancelled</option></select></label>
        <button type="submit" disabled={loading} className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">Apply filters</button>
      </form>
      {error && <p role="alert" className="mt-5 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {loading ? <p className="mt-6 text-sm text-ink/60">Loading events…</p> : events.length === 0 ? <p className="mt-6 text-sm text-ink/60">No events found.</p> : <div className="mt-6 overflow-x-auto"><table className="w-full min-w-[1000px] text-left text-sm"><thead className="border-b border-ink/10 text-xs uppercase text-ink/45"><tr><th className="py-3">Occurred</th><th>Provider</th><th>Model</th><th>Feature</th><th>Customer ID</th><th>Status</th><th>Input</th><th>Output</th><th>Duration</th><th>Cost</th></tr></thead><tbody>{events.map((item) => <tr key={item.id} className="border-b border-ink/10 last:border-0"><td className="py-3">{new Date(item.occurred_at).toLocaleString()}</td><td>{item.provider}</td><td>{item.model}</td><td>{item.feature}</td><td>{item.customer_external_id ?? "—"}</td><td className="capitalize">{item.status}</td><td>{item.input_tokens}</td><td>{item.output_tokens}</td><td>{item.duration_ms == null ? "—" : `${item.duration_ms} ms`}</td><td><EventCostCell cost={item.cost} /></td></tr>)}</tbody></table></div>}
      {nextCursor && !loading && <button type="button" onClick={() => void load(filters, nextCursor)} className="mt-5 rounded-xl border border-ink/20 px-4 py-2 text-sm font-semibold">Next page</button>}
    </section>
  );
}
