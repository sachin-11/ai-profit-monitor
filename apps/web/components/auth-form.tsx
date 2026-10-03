"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, api } from "@/lib/api";

type AuthMode = "login" | "register";

export function AuthForm({ mode }: { mode: AuthMode }) {
  const router = useRouter();
  const isRegister = mode === "register";
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!email || !password) {
      setError("Email and password are required.");
      return;
    }
    if (isRegister && password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }

    setLoading(true);
    try {
      if (isRegister) {
        const displayName = String(form.get("display_name") ?? "").trim();
        const organizationName = String(form.get("organization_name") ?? "").trim();
        if (!displayName || !organizationName) {
          setError("Display name and organization name are required.");
          return;
        }
        await api.auth.register({
          display_name: displayName,
          email,
          password,
          organization_name: organizationName,
        });
      } else {
        await api.auth.login({ email, password });
      }
      router.replace("/app");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to complete the request.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <section className="w-full max-w-md rounded-[2rem] border border-white/80 bg-white/90 p-8 shadow-card md:p-10">
        <Link href="/" className="text-sm font-semibold text-ink/60">← AI Profit Monitor</Link>
        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-ink">
          {isRegister ? "Create your workspace" : "Welcome back"}
        </h1>
        <p className="mt-2 text-sm leading-6 text-ink/60">
          {isRegister ? "Start with an owner account for your organization." : "Sign in to your organization workspace."}
        </p>
        <form className="mt-8 space-y-5" onSubmit={submit} noValidate>
          {isRegister && <label className="block text-sm font-medium text-ink">Display name<input name="display_name" autoComplete="name" required maxLength={100} className="mt-2 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink focus:ring-2 focus:ring-mint/40" /></label>}
          <label className="block text-sm font-medium text-ink">{isRegister ? "Work email" : "Email"}<input name="email" type="email" autoComplete="email" required className="mt-2 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink focus:ring-2 focus:ring-mint/40" /></label>
          <label className="block text-sm font-medium text-ink">Password<input name="password" type="password" autoComplete={isRegister ? "new-password" : "current-password"} required minLength={isRegister ? 12 : 1} maxLength={1024} className="mt-2 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink focus:ring-2 focus:ring-mint/40" /></label>
          {isRegister && <label className="block text-sm font-medium text-ink">Organization name<input name="organization_name" autoComplete="organization" required maxLength={120} className="mt-2 w-full rounded-xl border border-ink/15 bg-white px-4 py-3 outline-none focus:border-ink focus:ring-2 focus:ring-mint/40" /></label>}
          {error && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
          <button type="submit" disabled={loading} className="w-full rounded-xl bg-ink px-4 py-3 font-semibold text-white transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60">{loading ? "Please wait…" : isRegister ? "Create account" : "Sign in"}</button>
        </form>
        <p className="mt-7 text-center text-sm text-ink/60">{isRegister ? "Already have an account?" : "New to AI Profit Monitor?"}{" "}<Link href={isRegister ? "/login" : "/register"} className="font-semibold text-ink underline">{isRegister ? "Sign in" : "Create account"}</Link></p>
      </section>
    </main>
  );
}
