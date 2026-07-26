// The Risk Manager's live posture.
//
// This screen used to render `config.risk` — the same values the Settings tab
// already lists in full — with a placeholder promising that risk events "will
// stream here". Meanwhile the platform's actual safety state (kill switch,
// circuit breaker, emergency mode, what the manager has been approving and
// rejecting) was already served by /api/v1/risk/status and shown nowhere at
// all. That is the more consequential thing to have on screen, so it is what
// this shows now — and it stops Risk being a second view of Settings.

import { useEffect, useState } from "react";
import { api, type RiskDecision, type RiskLive } from "../api/client";
import { Badge, PageHeader, Panel, Placeholder, Row, StatusDot } from "../ui";

function pct(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "—" : `${value.toFixed(2)}%`;
}

/** The kill switch is a level, and the level is the headline. */
function KillSwitch({ live }: { live: RiskLive }) {
  const level = live.kill_switch_level ?? 0;
  const tone = level === 0 ? "success" : level >= 3 ? "danger" : "warn";
  return (
    <span className="flex items-center gap-2">
      <Badge tone={tone}>{live.kill_switch_label ?? `level ${level}`}</Badge>
      {live.kill_switch_reason && (
        <span className="text-xs text-hades-muted">{live.kill_switch_reason}</span>
      )}
    </span>
  );
}

export function RiskScreen() {
  const [live, setLive] = useState<RiskLive | null>(null);
  const [running, setRunning] = useState(false);
  const [decisions, setDecisions] = useState<RiskDecision[]>([]);

  useEffect(() => {
    const load = () => {
      api
        .riskStatus()
        .then((r) => {
          setLive(r.live);
          setRunning(r.running);
        })
        .catch(() => undefined);
      api
        .riskDecisions()
        .then((r) => setDecisions(r.decisions))
        .catch(() => undefined);
    };
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const l = live ?? {};

  return (
    <div>
      <PageHeader
        title="Risk"
        subtitle="The Risk Manager's live posture — the only component that authorises a trade."
      />

      <div className="mb-6 flex items-center gap-2">
        <StatusDot status={running ? "healthy" : "unknown"} />
        <span className="text-sm text-gray-200">
          {running ? "Risk Manager reporting" : "No snapshot — is the worker running?"}
        </span>
        {l.emergency_mode && <Badge tone="danger">EMERGENCY MODE</Badge>}
        {l.circuit_breaker_open && <Badge tone="danger">CIRCUIT BREAKER OPEN</Badge>}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Safety state">
          <Row label="Kill switch" value={<KillSwitch live={l} />} />
          <Row
            label="Circuit breaker"
            value={l.circuit_breaker_open ? "open" : "closed"}
            danger={l.circuit_breaker_open}
          />
          {(l.circuit_breaker_reasons ?? []).length > 0 && (
            <Row label="Breaker reasons" value={(l.circuit_breaker_reasons ?? []).join(", ")} />
          )}
          <Row
            label="Emergency mode"
            value={l.emergency_mode ? "active" : "off"}
            danger={l.emergency_mode}
          />
          <Row label="Consecutive losses" value={String(l.consecutive_losses ?? 0)} />
        </Panel>

        <Panel title="Exposure vs limits">
          <Row label="Open positions" value={String(l.open_positions ?? 0)} />
          <Row label="Portfolio exposure" value={pct(l.portfolio_exposure_pct)} />
          <Row label="Daily loss" value={pct(l.daily_loss_pct)} />
          <Row label="Drawdown" value={pct(l.drawdown_pct)} />
          <Row
            label="This session"
            value={`${l.approvals_session ?? 0} approved · ${l.rejections_session ?? 0} rejected`}
          />
        </Panel>
      </div>

      <div className="mt-6">
        <Panel title="Recent decisions">
          {decisions.length === 0 && <Placeholder note="No risk decisions recorded yet." />}
          {decisions.map((d, i) => (
            <Row
              key={`${d.mint}-${d.at}-${i}`}
              label={
                <span>
                  <span className="text-gray-300">{d.symbol || d.mint.slice(0, 8)}</span>{" "}
                  <span className="text-hades-muted">
                    {d.at?.replace("T", " ").slice(0, 19) ?? ""}
                  </span>
                </span>
              }
              value={
                <span className="flex items-center gap-2">
                  <Badge tone={d.decision === "approve" ? "success" : "warn"}>{d.decision}</Badge>
                  <span className="text-xs text-hades-muted">
                    {d.reject_reason || d.headline || d.strategy || ""}
                  </span>
                </span>
              }
            />
          ))}
        </Panel>
      </div>
    </div>
  );
}
