// Small, reusable presentational primitives shared across screens. Kept
// dependency-free and minimal so the dashboard stays fast.

import type { ReactNode } from "react";

export function Panel({
  title,
  actions,
  children,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-white/5 bg-hades-panel p-6">
      {title && (
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-hades-muted">
            {title}
          </h2>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Row({
  label,
  value,
  danger,
}: {
  label: ReactNode;
  value: ReactNode;
  danger?: boolean;
}) {
  return (
    <div className="flex justify-between border-b border-white/5 py-2 text-sm last:border-0">
      <span className="text-hades-muted">{label}</span>
      <span className={danger ? "font-semibold text-hades-accent" : "text-gray-200"}>
        {value}
      </span>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  healthy: "bg-emerald-500",
  degraded: "bg-amber-500",
  unhealthy: "bg-red-500",
  unknown: "bg-gray-500",
};

export function StatusDot({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? STATUS_COLORS.unknown;
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />;
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "danger" | "success" | "warn";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-white/5 text-gray-300",
    danger: "bg-red-950/60 text-red-300 border border-red-800",
    success: "bg-emerald-950/50 text-emerald-300 border border-emerald-800",
    warn: "bg-amber-950/50 text-amber-300 border border-amber-800",
  };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight text-gray-100">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-hades-muted">{subtitle}</p>}
    </div>
  );
}

// Placeholder used by screens whose live data arrives in later phases. It makes
// the "structure only" intent explicit rather than showing fake data.
export function Placeholder({ note }: { note: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/10 bg-black/20 p-8 text-center">
      <p className="text-sm text-hades-muted">{note}</p>
      <p className="mt-1 text-xs text-hades-muted/60">
        Structure prepared — live data arrives in a later phase.
      </p>
    </div>
  );
}
