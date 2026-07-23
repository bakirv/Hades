import { useEffect, useState } from "react";
import { api, type Health } from "../api/client";
import { PageHeader, Panel, Row, StatusDot } from "../ui";

export function HealthScreen() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  return (
    <div>
      <PageHeader
        title="Health"
        subtitle="Dependency and resource probes (driven by the Watchdog)."
      />
      <Panel title="Components">
        <div className="mb-3 flex items-center gap-2">
          <StatusDot status={health?.status ?? "unknown"} />
          <span className="text-sm text-gray-200">Overall: {health?.status ?? "unknown"}</span>
        </div>
        {(health?.components ?? []).map((c) => (
          <Row
            key={c.name}
            label={c.name}
            value={
              <span className="flex items-center gap-2">
                <StatusDot status={c.status} /> {c.status} · {c.detail}
              </span>
            }
          />
        ))}
        {!health && <p className="text-sm text-hades-muted">Loading…</p>}
      </Panel>
    </div>
  );
}
