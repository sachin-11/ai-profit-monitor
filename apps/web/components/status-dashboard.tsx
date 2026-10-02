"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

type CheckState = "loading" | "online" | "offline";

interface StatusState {
  api: CheckState;
  database: CheckState;
}

const INITIAL_STATUS: StatusState = { api: "loading", database: "loading" };

function StatusRow({ label, state }: { label: string; state: CheckState }) {
  const labels: Record<CheckState, string> = {
    loading: "Checking…",
    online: "Operational",
    offline: "Unavailable",
  };
  const dotStyles: Record<CheckState, string> = {
    loading: "bg-amber-400 animate-pulse",
    online: "bg-emerald-500",
    offline: "bg-rose-500",
  };

  return (
    <div className="flex items-center justify-between border-b border-ink/10 py-5 last:border-0">
      <span className="text-sm font-medium text-ink/70">{label}</span>
      <span className="flex items-center gap-2 text-sm font-semibold text-ink">
        <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${dotStyles[state]}`} />
        {labels[state]}
      </span>
    </div>
  );
}

export function StatusDashboard() {
  const [status, setStatus] = useState<StatusState>(INITIAL_STATUS);

  useEffect(() => {
    let active = true;

    async function loadStatus() {
      const [health, readiness] = await Promise.allSettled([api.health(), api.readiness()]);
      if (!active) return;

      setStatus({
        api:
          health.status === "fulfilled" && health.value.data.status === "healthy"
            ? "online"
            : "offline",
        database:
          readiness.status === "fulfilled" && readiness.value.data.database === "available"
            ? "online"
            : "offline",
      });
    }

    void loadStatus();
    return () => {
      active = false;
    };
  }, []);

  return (
    <aside className="rounded-3xl bg-ink p-7 text-white md:p-8" aria-label="System status">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-mint">Live status</p>
      <h2 className="mt-3 text-2xl font-semibold tracking-tight">System checks</h2>
      <p className="mt-2 text-sm leading-6 text-white/55">Local API and data layer connectivity.</p>
      <div className="mt-6 rounded-2xl bg-white/[0.07] px-5">
        <StatusRow label="Backend API" state={status.api} />
        <StatusRow label="PostgreSQL" state={status.database} />
      </div>
    </aside>
  );
}

