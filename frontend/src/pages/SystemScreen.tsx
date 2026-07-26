// The platform's own state: what is running, and is it healthy.
//
// The health panel here used to be duplicated by a whole separate Health screen
// that rendered the same `/health` components. A hardcoded "Services" badge list
// sat beside it, which looked like status and was in fact a string array — it
// stayed green while a service was down. Both are gone: the probes below are
// live, and they are the only claim this screen makes about what is running.

import { useEffect, useState } from "react";
import { api, type Health, type Status } from "../api/client";
import { Badge, PageHeader, Panel, Row, StatusDot } from "../ui";

export function SystemScreen() {
  const [status, setStatus] = useState<Status | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const load = () => {
      api.status().then(setStatus).catch(() => undefined);
      api.health().then(setHealth).catch(() => undefined);
      api.info().then(setInfo).catch(() => undefined);
    };
    load();
    // Health is the reason to be on this screen; a snapshot from page load is
    // not health, it is a photograph of it.
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
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

        <Panel title="Health">
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
                  <StatusDot status={c.status} />
                  <span>{c.status}</span>
                  <span className="text-xs text-hades-muted">{c.detail}</span>
                </span>
              }
            />
          ))}
          {!health && <p className="text-sm text-hades-muted">Loading…</p>}
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
