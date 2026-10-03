"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { MeData, api } from "@/lib/api";
import { Project, ProjectEnvironment, projectsApi } from "@/lib/projects-api";

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString();
}

export function ProjectsPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<MeData | null>(null);
  const [organizationIndex, setOrganizationIndex] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadedOrganizationId, setLoadedOrganizationId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const membership = profile?.memberships[organizationIndex];
  const canManage = membership?.role === "owner" || membership?.role === "admin";
  const loading = !profile || Boolean(membership && loadedOrganizationId !== membership.organization.id);

  useEffect(() => {
    let active = true;
    api.auth.me().then((result) => {
      if (active) setProfile(result.data);
    }).catch(() => {
      if (active) router.replace("/login");
    });
    return () => { active = false; };
  }, [router]);

  useEffect(() => {
    if (!membership) return;
    let active = true;
    projectsApi.list(membership.organization.id).then((result) => {
      if (active) {
        setProjects(result.data.projects);
        setError("");
      }
    }).catch(() => {
      if (active) setError("Could not load projects. Please retry.");
    }).finally(() => {
      if (active) setLoadedOrganizationId(membership.organization.id);
    });
    return () => { active = false; };
  }, [membership, profile]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!membership) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      setError("Project name is required.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const result = await projectsApi.create(membership.organization.id, {
        name,
        environment: String(form.get("environment")) as ProjectEnvironment,
        description: String(form.get("description") ?? "").trim(),
      });
      setProjects((current) => [result.data.project, ...current]);
      formElement.reset();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create project.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-10">
      <div className="mx-auto max-w-6xl">
        <Link href="/app" className="text-sm font-semibold text-ink/60">← Workspace</Link>
        <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Workspace</p><h1 className="mt-2 text-4xl font-semibold text-ink">Projects</h1></div>
          {profile && profile.memberships.length > 1 && <label className="text-sm font-medium text-ink">Organization<select aria-label="Organization" value={organizationIndex} onChange={(event) => setOrganizationIndex(Number(event.target.value))} className="ml-3 rounded-xl border border-ink/15 bg-white px-4 py-2">{profile.memberships.map((item, index) => <option key={item.id} value={index}>{item.organization.name}</option>)}</select></label>}
        </div>
        {membership && <p className="mt-3 text-ink/60">{membership.organization.name} · {membership.role}</p>}
        {error && <p role="alert" className="mt-6 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}

        {canManage && <section className="mt-8 rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card" aria-label="Create project">
          <h2 className="text-xl font-semibold">Create a project</h2>
          <form onSubmit={create} className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="text-sm font-medium">Project name<input name="name" required maxLength={120} className="mt-2 w-full rounded-xl border border-ink/15 px-4 py-3" /></label>
            <label className="text-sm font-medium">Environment<select name="environment" className="mt-2 w-full rounded-xl border border-ink/15 px-4 py-3"><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option></select></label>
            <label className="text-sm font-medium md:col-span-2">Description (optional)<textarea name="description" maxLength={1000} rows={2} className="mt-2 w-full rounded-xl border border-ink/15 px-4 py-3" /></label>
            <button type="submit" disabled={creating} className="w-fit rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">{creating ? "Creating…" : "Create project"}</button>
          </form>
        </section>}

        <section className="mt-8" aria-label="Project list">
          {loading ? <p className="text-ink/60">Loading projects…</p> : projects.length === 0 ? <p className="rounded-3xl bg-white/90 p-8 text-ink/60">No projects yet.</p> : <div className="grid gap-4 md:grid-cols-2">{projects.map((project) => <Link key={project.id} href={`/app/projects/${project.id}`} className="rounded-3xl border border-white/80 bg-white/90 p-6 shadow-card transition hover:border-ink/20"><h2 className="text-xl font-semibold text-ink">{project.name}</h2><p className="mt-2 text-sm capitalize text-ink/60">{project.environment} · {project.is_active ? "Active" : "Inactive"}</p><p className="mt-3 text-xs text-ink/45">Created {dateLabel(project.created_at)}</p></Link>)}</div>}
        </section>
      </div>
    </main>
  );
}
