import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PageHeader, Panel, Row } from "../ui";

export function ConfigScreen() {
  const [config, setConfig] = useState<Record<string, Record<string, unknown>> | null>(null);

  useEffect(() => {
    api
      .config()
      .then((c) => setConfig(c as Record<string, Record<string, unknown>>))
      .catch(() => undefined);
  }, []);

  return (
    <div>
      <PageHeader
        title="Configuration"
        subtitle="Non-secret configuration posture (secrets are never exposed)."
      />
      <div className="grid gap-6 md:grid-cols-2">
        {config &&
          Object.entries(config).map(([section, values]) => (
            <Panel key={section} title={section}>
              {Object.entries(values).map(([k, v]) => (
                <Row key={k} label={k} value={String(Array.isArray(v) ? v.join(", ") : v)} />
              ))}
            </Panel>
          ))}
        {!config && <p className="text-sm text-hades-muted">Loading…</p>}
      </div>
    </div>
  );
}
