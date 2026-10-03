"use client";

import { FormEvent, useEffect, useState } from "react";

import { ProjectApiKey, projectsApi } from "@/lib/projects-api";

export function ApiKeysSection({ projectId }: { projectId: string }) {
  const [keys, setKeys] = useState<ProjectApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [oneTimeKey, setOneTimeKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    projectsApi.keys(projectId).then((result) => {
      if (active) setKeys(result.data.api_keys);
    }).catch(() => {
      if (active) setError("Could not load API keys.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [projectId]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("name") ?? "").trim();
    const expiry = String(form.get("expires_at") ?? "");
    if (!name) {
      setError("API key name is required.");
      return;
    }
    setSaving(true);
    setError("");
    setOneTimeKey(null);
    try {
      const result = await projectsApi.createKey(projectId, {
        name,
        ...(expiry ? { expires_at: new Date(expiry).toISOString() } : {}),
      });
      setKeys((current) => [result.data.api_key, ...current]);
      setOneTimeKey(result.data.raw_key);
      formElement.reset();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create API key.");
    } finally {
      setSaving(false);
    }
  }

  async function revoke(key: ProjectApiKey) {
    if (!window.confirm(`Revoke API key “${key.name}”? Integrations using it will stop working.`)) return;
    setError("");
    try {
      const result = await projectsApi.revokeKey(projectId, key.id);
      setKeys((current) => current.map((item) => item.id === key.id ? result.data.api_key : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not revoke API key.");
    }
  }

  async function copyOneTimeKey() {
    if (!oneTimeKey) return;
    try {
      await navigator.clipboard.writeText(oneTimeKey);
    } catch {
      setError("Copy failed. Please select and copy the key manually.");
    }
  }

  return (
    <section className="rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card" aria-label="API keys">
      <h2 className="text-2xl font-semibold">API keys</h2>
      <p className="mt-2 text-sm text-ink/60">Project keys authenticate event ingestion. Rotate by creating a new key, updating your integration, then revoking the old one.</p>
      {error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {oneTimeKey && <div className="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-4" aria-label="New API key">
        <p className="text-sm font-semibold text-ink">Copy this key now. It cannot be retrieved later.</p>
        <code className="mt-3 block break-all rounded-lg bg-white p-3 text-sm text-ink">{oneTimeKey}</code>
        <div className="mt-3 flex gap-3"><button type="button" onClick={copyOneTimeKey} className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white">Copy key</button><button type="button" onClick={() => setOneTimeKey(null)} className="rounded-lg border border-ink/20 px-4 py-2 text-sm font-semibold">Dismiss</button></div>
      </div>}
      <form onSubmit={create} className="mt-6 grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <label className="text-sm font-medium">Key name<input name="name" required maxLength={100} className="mt-2 w-full rounded-xl border border-ink/15 px-4 py-3" /></label>
        <label className="text-sm font-medium">Expires at (optional)<input name="expires_at" type="datetime-local" className="mt-2 w-full rounded-xl border border-ink/15 px-4 py-3" /></label>
        <button type="submit" disabled={saving} className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">{saving ? "Creating…" : "Create key"}</button>
      </form>
      <div className="mt-6">
        {loading ? <p className="text-sm text-ink/60">Loading API keys…</p> : keys.length === 0 ? <p className="text-sm text-ink/60">No API keys yet.</p> : <ul className="divide-y divide-ink/10">{keys.map((key) => <li key={key.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div><p className="font-semibold">{key.name}</p><p className="text-xs text-ink/55">Prefix {key.key_prefix} · Created {new Date(key.created_at).toLocaleDateString()} · Last used {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : "never"}{key.expires_at ? ` · Expires ${new Date(key.expires_at).toLocaleDateString()}` : ""}</p></div>{key.revoked_at ? <span className="text-sm text-ink/50">Revoked</span> : <button type="button" onClick={() => revoke(key)} className="rounded-lg border border-rose-200 px-3 py-2 text-sm font-medium text-rose-700">Revoke</button>}</li>)}</ul>}
      </div>
    </section>
  );
}
