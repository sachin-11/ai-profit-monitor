"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MeData, api } from "@/lib/api";

export function AppShell() {
  const router = useRouter();
  const [profile, setProfile] = useState<MeData | null>(null);
  const [selectedMembership, setSelectedMembership] = useState(0);
  const [error, setError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    let active = true;
    api.auth.me().then((response) => {
      if (active) setProfile(response.data);
    }).catch(() => {
      if (active) router.replace("/login");
    });
    return () => { active = false; };
  }, [router]);

  async function logout() {
    setLoggingOut(true);
    setError("");
    try {
      await api.auth.logout();
      router.replace("/login");
      router.refresh();
    } catch {
      setError("Could not sign out. Please try again.");
      setLoggingOut(false);
    }
  }

  if (!profile) return <main className="grid min-h-screen place-items-center px-6"><p className="text-sm font-medium text-ink/60">Loading workspace…</p></main>;
  const membership = profile.memberships[selectedMembership];
  return (
    <main className="min-h-screen px-6 py-10 md:px-10"><div className="mx-auto max-w-6xl">
      <header className="flex flex-col gap-5 rounded-3xl bg-ink px-7 py-6 text-white sm:flex-row sm:items-center sm:justify-between">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-mint">AI Profit Monitor</p><h1 className="mt-2 text-2xl font-semibold">Application workspace</h1></div>
        <button type="button" onClick={logout} disabled={loggingOut} className="rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10 disabled:opacity-60">{loggingOut ? "Signing out…" : "Sign out"}</button>
      </header>
      {error && <p role="alert" className="mt-5 rounded-xl bg-rose-50 p-4 text-rose-700">{error}</p>}
      <section className="mt-8 grid gap-6 md:grid-cols-2">
        <article className="rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Profile</p><h2 className="mt-4 text-2xl font-semibold text-ink">{profile.user.display_name}</h2><p className="mt-1 text-ink/60">{profile.user.email}</p></article>
        <article className="rounded-3xl border border-white/80 bg-white/90 p-7 shadow-card">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Organization</p>
          {profile.memberships.length > 1 && <label className="mt-4 block text-sm font-medium text-ink">Current organization<select aria-label="Current organization" value={selectedMembership} onChange={(event) => setSelectedMembership(Number(event.target.value))} className="mt-2 w-full rounded-xl border border-ink/15 bg-white px-4 py-3">{profile.memberships.map((item, index) => <option value={index} key={item.id}>{item.organization.name}</option>)}</select></label>}
          {membership ? <div className="mt-4"><h2 className="text-2xl font-semibold text-ink">{membership.organization.name}</h2><p className="mt-2 inline-flex rounded-full bg-mint/20 px-3 py-1 text-sm font-semibold capitalize text-ink">{membership.role}</p></div> : <p className="mt-4 text-ink/60">No organization membership found.</p>}
        </article>
      </section>
      <Link href="/app/projects" className="mt-8 inline-flex rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white">View projects</Link>
    </div></main>
  );
}
