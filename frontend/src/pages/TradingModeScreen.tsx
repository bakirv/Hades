import { useEffect, useState } from "react";
import { api, type ModeStatus, type ReadinessReport } from "../api/client";
import { ModeSwitch } from "../components/ModeSwitch";
import { Badge, PageHeader, Panel, Row } from "../ui";

export function TradingModeScreen() {
  const [mode, setMode] = useState<ModeStatus | null>(null);
  const [report, setReport] = useState<ReadinessReport | null>(null);

  useEffect(() => {
    api.tradingMode().then(setMode).catch(() => undefined);
  }, []);

  const runVerify = () => api.verifyLive().then(setReport).catch(() => undefined);

  return (
    <div>
      <PageHeader
        title="Trading mode"
        subtitle="Paper is always safe. Live is hard-gated: env flag + verification + confirmation."
      />
      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Current mode" actions={<ModeSwitch />}>
          <Row label="Effective mode" value={mode?.mode ?? "…"} />
          <Row label="Is live" value={String(mode?.is_live)} danger={mode?.is_live} />
          <Row label="Live env gate" value={String(mode?.live_gate_enabled)} />
        </Panel>

        <Panel
          title="Live readiness"
          actions={
            <button
              onClick={runVerify}
              className="rounded-md border border-white/10 px-3 py-1 text-xs text-gray-200 hover:bg-white/5"
            >
              Run verification
            </button>
          }
        >
          {!report && <p className="text-sm text-hades-muted">Run verification to see checks.</p>}
          {report && (
            <>
              <div className="mb-3">
                <Badge tone={report.ready ? "success" : "danger"}>
                  {report.ready ? "READY" : "NOT READY"}
                </Badge>
              </div>
              {report.checks.map((c) => (
                <Row
                  key={c.name}
                  label={`${c.ok ? "✓" : "✕"} ${c.name}${c.required ? "" : " (optional)"}`}
                  value={c.detail}
                  danger={c.required && !c.ok}
                />
              ))}
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
