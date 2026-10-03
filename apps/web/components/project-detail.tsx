"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, MembershipRole } from "@/lib/api";
import { Project, projectsApi } from "@/lib/projects-api";
import { ApiKeysSection } from "@/components/api-keys-section";
import { RecentEvents } from "@/components/recent-events";

export function ProjectDetail({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [role, setRole] = useState<MembershipRole | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    projectsApi.get(projectId).then((result) => {
      if (!active) return;
      setProject(result.data.project);
      setRole(result.data.role);
    }).catch((caught) => {
      if (!active) return;
      if (caught instanceof ApiError && caught.status === 401) router.replace("/login");
      else setError(caught instanceof ApiError && caught.status === 404 ? "Project not found or access unavailable." : "Could not load project.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [projectId, router]);

  if (loading) return <main className="grid min-h-screen place-items-center"><p>Loading project…</p></main>;
  if (error || !project) return <main className="mx-auto max-w-5xl px-6 py-12"><Link href="/app/projects" className="text-sm font-semibold">← Projects</Link><p role="alert" className="mt-6 rounded-xl bg-rose-50 p-4 text-rose-700">{error || "Project not found."}</p></main>;

  const canManage = role === "owner" || role === "admin";
  return (
    <main className="min-h-screen px-6 py-10 md:px-10"><div className="mx-auto max-w-6xl space-y-7">
      <Link href="/app/projects" className="text-sm font-semibold text-ink/60">← Projects</Link>
      <header className="rounded-3xl bg-ink p-8 text-white"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-mint">{project.environment} project</p><h1 className="mt-3 text-4xl font-semibold">{project.name}</h1><p className="mt-3 text-white/65">{project.description || "No description"}</p><p className="mt-4 text-sm">Status: {project.is_active ? "Active" : "Inactive"}</p></header>
      {canManage ? <ApiKeysSection projectId={projectId} /> : <section className="rounded-3xl bg-white/90 p-7 shadow-card"><h2 className="text-2xl font-semibold">API keys</h2><p className="mt-2 text-sm text-ink/60">Only organization owners and admins can manage API keys.</p></section>}
      <RecentEvents projectId={projectId} />
      <section className="rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card" aria-label="Integration example">
        <h2 className="text-2xl font-semibold">Integration example</h2>
        <p className="mt-2 text-sm text-ink/60">
          Send usage metadata only. Replace the key and timestamp; do not include prompts or model responses.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-xl bg-ink p-5 text-sm text-white">
          <code>{`curl -X POST http://localhost:8000/api/v1/ingest/events -H "Authorization: Bearer YOUR_PROJECT_API_KEY" -H "Content-Type: application/json" -d '{"client_event_id":"event-123","schema_version":1,"provider":"openai","model":"gpt-4o-mini","feature":"assistant","status":"success","input_tokens":42,"output_tokens":12,"occurred_at":"CURRENT_UTC_TIMESTAMP"}'`}</code>
        </pre>
      </section>
    </div></main>
  );
}
