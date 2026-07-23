import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader, Panel, Placeholder, Row } from "../ui";

export function RiskScreen() {
  const [risk, setRisk] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api
      .config()
      .then((c) => setRisk((c as Record<string, Record<string, unknown>>).risk))
      .catch(() => undefined);
  }, []);

  return (
    <div>
      <PageHeader title="Risk" subtitle="Risk limits and events. The Risk Manager decides." />
      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Configured limits">
          {risk ? (
            Object.entries(risk).map(([k, v]) => <Row key={k} label={k} value={String(v)} />)
          ) : (
            <p className="text-sm text-hades-muted">Loading…</p>
          )}
        </Panel>
        <Panel title="Risk events">
          <Placeholder note="Risk events (kill switch, breaches) will stream here." />
        </Panel>
      </div>
    </div>
  );
}
