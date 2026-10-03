import Link from "next/link";

import { StatusDashboard } from "@/components/status-dashboard";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-5xl overflow-hidden rounded-[2rem] border border-white/80 bg-white/80 shadow-card backdrop-blur">
        <div className="grid gap-12 px-8 py-12 md:grid-cols-[1.2fr_0.8fr] md:px-14 md:py-16">
          <div className="flex flex-col justify-center">
            <div className="mb-7 flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.2em] text-ink/60">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-ink text-mint">AP</span>
              Cost intelligence
            </div>
            <h1 className="max-w-xl text-5xl font-semibold leading-[1.05] tracking-[-0.045em] text-ink md:text-6xl">
              AI Profit Monitor
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-ink/65">
              See the true AI API cost behind every customer and feature, so growth and margin move in the same direction.
            </p>
            <div className="mt-10 inline-flex w-fit items-center gap-2 rounded-full bg-mint/20 px-4 py-2 text-sm font-medium text-ink">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Foundation environment
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/register" className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white">Create account</Link>
              <Link href="/login" className="rounded-xl border border-ink/15 px-5 py-3 text-sm font-semibold text-ink">Sign in</Link>
            </div>
          </div>
          <StatusDashboard />
        </div>
      </section>
    </main>
  );
}

