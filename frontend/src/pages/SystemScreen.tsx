import { useEffect, useState } from "react";
import { api, type Health, type Status } from "../api/client";
import { Badge, PageHeader, Panel, Row, StatusDot } from "../ui";

const SERVICES = [
  "postgres", "redis", "api", "dashboard", "engine",
  "watchdog", "scheduler", "worker", "notification",
];

export function SystemScreen() {
  const [status, setStatus] = useState<Status | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
    api.info().then(setInfo).catch(() => undefined);
  }, []);

  const contexts = (info?.contexts as string[]) ?? [];

  return (
    <div>
      <PageHeader title="System status" subtitle="Runtime posture and platform topology." />
      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Runtime">
          <Row label="Version" value={status?.version ?? "…"} />
          <Row label="Environment" value={status?.environment ?? "…"} />
          <Row label="Instance" value={status?.instance_id ?? "…"} />
          <Row label="Trading mode" value={status?.trading_mode ?? "…"} />
          <Row label="Live enabled" value={String(status?.is_live)} danger={status?.is_live} />
          <Row label="Event bus" value={status?.event_bus_transport ?? "…"} />
        </Panel>

        <Panel title="Aggregate health">
          <div className="mb-3 flex items-center gap-2">
            <StatusDot status={health?.status ?? "unknown"} />
            <span className="text-sm text-gray-200">{health?.status ?? "unknown"}</span>
          </div>
          {(health?.components ?? []).map((c) => (
            <Row
              key={c.name}
              label={c.name}
              value={
                <span className="flex items-center gap-2">
                  <StatusDot status={c.status} /> {c.detail}
                </span>
              }
            />
          ))}
        </Panel>

        <Panel title={`Services (${SERVICES.length})`}>
          <div className="flex flex-wrap gap-2">
            {SERVICES.map((s) => (
              <Badge key={s}>{s}</Badge>
            ))}
          </div>
        </Panel>

        <Panel title={`Bounded contexts (${contexts.length})`}>
          <div className="flex flex-wrap gap-2">
            {contexts.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
