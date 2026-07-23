import { useEffect, useState } from "react";
import {
  api,
  type CommitteeModel,
  type CommitteePredictionDetail,
  type CommitteePredictionSummary,
  type CommitteeStatus,
  type DriftAlert,
} from "../api/client";
import { Badge, PageHeader, Panel, Placeholder } from "../ui";

// AI Committee — the explainable quantitative brain. Read-only: it shows the
// probabilities and evidence the committee produced. It never decides a trade —
// the Risk Manager (a later phase) is the sole decision-maker.

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/20 p-4">
      <div className="text-xs uppercase tracking-wide text-hades-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-gray-100">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-hades-muted/70">{hint}</div>}
    </div>
  );
}

function pct(v: number | undefined): string {
  return v === undefined ? "—" : `${Math.round(v * 100)}%`;
}

function shortAddr(a: string): string {
  return a.length > 12 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a;
}

const REGIME_TONE: Record<string, "neutral" | "success" | "warn" | "danger"> = {
  bull: "success",
  fomo: "success",
  sideways: "neutral",
  low_liquidity: "warn",
  highly_volatile: "warn",
  bear: "danger",
  panic: "danger",
  unknown: "neutral",
};

// A probability bar. `bad` inverts the colour (high P(SL) is bad).
function ProbBar({ label, value, bad }: { label: string; value: number; bad?: boolean }) {
  const v = Math.max(0, Math.min(1, value));
  const color = bad
    ? v >= 0.5
      ? "bg-red-500"
      : v >= 0.3
        ? "bg-amber-500"
        : "bg-emerald-500"
    : v >= 0.6
      ? "bg-emerald-500"
      : v >= 0.4
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <div className="py-1.5">
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-hades-muted">{label}</span>
        <span className="text-gray-300">{Math.round(v * 100)}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div className={`h-full ${color}`} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

export function AIScreen() {
  const [status, setStatus] = useState<CommitteeStatus | null>(null);
  const [models, setModels] = useState<CommitteeModel[]>([]);
  const [predictions, setPredictions] = useState<CommitteePredictionSummary[]>([]);
  const [drift, setDrift] = useState<DriftAlert[]>([]);
  const [detail, setDetail] = useState<CommitteePredictionDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [s, m, p, d] = await Promise.all([
          api.committeeStatus(),
          api.committeeModels(),
          api.committeePredictions(25),
          api.committeeDrift(),
        ]);
        if (!active) return;
        setStatus(s);
        setModels(m.models);
        setPredictions(p.predictions);
        setDrift(d.drift);
        setError(false);
      } catch {
        if (active) setError(true);
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, []);

  const openDetail = async (mint: string) => {
    try {
      setDetail(await api.committeePrediction(mint));
    } catch {
      setDetail(null);
    }
  };

  const last = status?.live.last_prediction;

  return (
    <div>
      <PageHeader
        title="AI Committee"
        subtitle="A committee of specialists produces probabilities and evidence — never a decision. The Risk Manager decides."
      />

      {error && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950/40 px-4 py-2 text-sm text-red-300">
          Committee API unreachable.
        </div>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Committee"
          value={status?.enabled ? "Active" : "Disabled"}
          hint={`${status?.live.members ?? 12} specialists + meta`}
        />
        <Stat
          label="Models"
          value={status?.models_total ?? 0}
          hint={`${status?.promoted_total ?? 0} promoted`}
        />
        <Stat
          label="Predictions"
          value={status?.predictions_total ?? 0}
          hint={`${status?.live.predictions_session ?? 0} this session`}
        />
        <Stat
          label="Shadow / Auto-train"
          value={`${status?.live.shadow_enabled ? "on" : "off"} / ${status?.live.auto_train ? "on" : "off"}`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Latest fused prediction">
          {last?.mint ? (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-sm text-gray-300">{shortAddr(last.mint)}</span>
                <Badge tone={REGIME_TONE[last.regime ?? "unknown"] ?? "neutral"}>
                  {(last.regime ?? "unknown").replace("_", " ")}
                </Badge>
              </div>
              <ProbBar label="P(ROI positive)" value={last.prob_roi_positive ?? 0} />
              <ProbBar label="P(hit take-profit)" value={last.prob_hit_tp ?? 0} />
              <ProbBar label="P(hit stop-loss)" value={last.prob_hit_sl ?? 0} bad />
              <ProbBar label="Confidence" value={last.confidence ?? 0} />
              <p className="mt-3 text-xs text-hades-muted">{last.headline}</p>
            </div>
          ) : (
            <Placeholder note="No prediction yet — the committee runs when a token completes analysis." />
          )}
        </Panel>

        <Panel title="Active models & registry">
          {models.length === 0 ? (
            <Placeholder note="No trained models yet — the committee runs on documented default weights until training produces a candidate." />
          ) : (
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {models.map((m) => (
                <div
                  key={m.model_id}
                  className="flex items-center justify-between rounded-md border border-white/5 bg-black/20 px-3 py-2 text-sm"
                >
                  <div>
                    <span className="text-gray-200">{m.name}</span>
                    <span className="ml-2 text-xs text-hades-muted">v{m.version}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {m.metrics?.auc !== undefined && (
                      <span className="text-xs text-hades-muted">
                        AUC {m.metrics.auc.toFixed(2)}
                      </span>
                    )}
                    <Badge
                      tone={
                        m.status === "promoted"
                          ? "success"
                          : m.status === "rejected"
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {m.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Recent predictions">
            {predictions.length === 0 ? (
              <Placeholder note="Predictions will appear as tokens flow through the pipeline." />
            ) : (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase text-hades-muted">
                    <tr>
                      <th className="py-1.5">Token</th>
                      <th>P(ROI+)</th>
                      <th>P(TP)</th>
                      <th>P(SL)</th>
                      <th>Conf</th>
                      <th>Regime</th>
                    </tr>
                  </thead>
                  <tbody>
                    {predictions.map((p, i) => (
                      <tr
                        key={`${p.mint}-${i}`}
                        className="cursor-pointer border-t border-white/5 hover:bg-white/5"
                        onClick={() => openDetail(p.mint)}
                      >
                        <td className="py-1.5 font-mono text-xs text-gray-300">
                          {shortAddr(p.mint)}
                        </td>
                        <td className="text-emerald-300">{pct(p.prob_roi_positive)}</td>
                        <td className="text-gray-300">{pct(p.prob_hit_tp)}</td>
                        <td className="text-red-300">{pct(p.prob_hit_sl)}</td>
                        <td className="text-gray-400">{pct(p.confidence)}</td>
                        <td>
                          <Badge tone={REGIME_TONE[p.regime] ?? "neutral"}>
                            {p.regime.replace("_", " ")}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        <Panel title="Model drift">
          {drift.length === 0 ? (
            <Placeholder note="No drift detected. The monitor watches data / feature / concept drift." />
          ) : (
            <div className="max-h-96 space-y-2 overflow-y-auto">
              {drift.map((d, i) => (
                <div key={i} className="rounded-md border border-white/5 bg-black/20 p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <Badge tone={d.triggered ? "warn" : "neutral"}>{d.kind}</Badge>
                    <span className="text-xs text-hades-muted">sev {d.severity.toFixed(2)}</span>
                  </div>
                  <p className="mt-1 text-xs text-hades-muted">{d.detail}</p>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {detail && <PredictionDetail detail={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function PredictionDetail({
  detail,
  onClose,
}: {
  detail: CommitteePredictionDetail;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-white/10 bg-hades-bg p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Committee verdict</h2>
            <p className="font-mono text-xs text-hades-muted">{detail.token.mint.address}</p>
          </div>
          <button onClick={onClose} className="text-hades-muted hover:text-gray-200">
            ✕
          </button>
        </div>

        <div className="mb-4 grid gap-3 sm:grid-cols-4">
          <Stat label="P(ROI+)" value={pct(detail.meta.prob_roi_positive)} />
          <Stat label="P(TP)" value={pct(detail.meta.prob_hit_tp)} />
          <Stat label="P(SL)" value={pct(detail.meta.prob_hit_sl)} />
          <Stat label="Confidence" value={pct(detail.confidence.final)} />
        </div>

        {detail.explanation && (
          <div className="mb-4 space-y-2 text-sm">
            <p className="text-gray-300">{detail.explanation.headline}</p>
            {detail.explanation.drivers.length > 0 && (
              <div>
                <div className="text-xs uppercase text-emerald-400">Drivers</div>
                <ul className="ml-4 list-disc text-hades-muted">
                  {detail.explanation.drivers.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {detail.explanation.risks.length > 0 && (
              <div>
                <div className="text-xs uppercase text-amber-400">Risks</div>
                <ul className="ml-4 list-disc text-hades-muted">
                  {detail.explanation.risks.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {detail.explanation.caveats.length > 0 && (
              <div>
                <div className="text-xs uppercase text-hades-muted">Caveats</div>
                <ul className="ml-4 list-disc text-hades-muted/80">
                  {detail.explanation.caveats.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="text-xs uppercase text-hades-muted">Specialist opinions</div>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {detail.opinions.map((o) => (
            <div key={o.member} className="rounded-md border border-white/5 bg-black/20 p-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-200">{o.member.replace("_", " ")}</span>
                <span className={o.abstained ? "text-hades-muted/50" : "text-gray-300"}>
                  {o.abstained ? "abstained" : `${Math.round(o.probability * 100)}%`}
                </span>
              </div>
              {!o.abstained && (
                <div className="mt-1 text-xs text-hades-muted">
                  conf {Math.round(o.confidence * 100)}% ·{" "}
                  {o.reasons
                    .slice(0, 2)
                    .map((r) => r.text)
                    .join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
