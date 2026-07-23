// Paper/Live switch. The switch can NEVER enable live directly: choosing Live
// opens a guarded flow that verifies readiness (env gate, wallet, RPC, risk),
// shows the checklist, and requires an explicit confirmation before the change
// is requested. Paper is always safe and switches immediately.

import { useEffect, useState } from "react";
import { api, type ModeStatus, type ReadinessReport } from "../api/client";
import { Badge } from "../ui";

export function ModeSwitch() {
  const [mode, setMode] = useState<ModeStatus | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => api.tradingMode().then(setMode).catch(() => undefined);
  useEffect(() => {
    refresh();
  }, []);

  const openLiveFlow = async () => {
    setShowModal(true);
    setConfirmed(false);
    setError(null);
    setVerifying(true);
    try {
      setReport(await api.verifyLive());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setVerifying(false);
    }
  };

  const switchToPaper = async () => {
    setBusy(true);
    setError(null);
    try {
      setMode(await api.changeMode("paper", true));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const confirmLive = async () => {
    setBusy(true);
    setError(null);
    try {
      setMode(await api.changeMode("live", true));
      setShowModal(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const isLive = mode?.mode === "live";

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-hades-muted">MODE</span>
      <Badge tone={isLive ? "danger" : "success"}>{mode?.mode?.toUpperCase() ?? "…"}</Badge>
      {isLive ? (
        <button
          onClick={switchToPaper}
          disabled={busy}
          className="rounded-md border border-white/10 px-3 py-1 text-xs text-gray-200 hover:bg-white/5 disabled:opacity-50"
        >
          Switch to Paper
        </button>
      ) : (
        <button
          onClick={openLiveFlow}
          className="rounded-md border border-red-800 bg-red-950/40 px-3 py-1 text-xs text-red-300 hover:bg-red-950/70"
        >
          Switch to Live…
        </button>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg rounded-xl border border-red-900/60 bg-hades-panel p-6">
            <h3 className="text-lg font-bold text-hades-accent">Enable LIVE trading?</h3>
            <p className="mt-2 text-sm text-hades-muted">
              Live mode places <span className="text-red-300">real on-chain orders</span> with
              real funds. This action is audited and announced. Verify every check below and
              confirm explicitly.
            </p>

            <div className="mt-4 space-y-2">
              {verifying && <p className="text-sm text-hades-muted">Running verification…</p>}
              {report?.checks.map((c) => (
                <div
                  key={c.name}
                  className="flex items-center justify-between rounded-md bg-black/30 px-3 py-2 text-sm"
                >
                  <span className="text-gray-200">
                    {c.ok ? "✓" : "✕"} {c.name}
                    {!c.required && <span className="ml-1 text-xs text-hades-muted">(optional)</span>}
                  </span>
                  <span className={c.ok ? "text-emerald-400" : "text-red-400"}>{c.detail}</span>
                </div>
              ))}
            </div>

            {report && !report.ready && (
              <p className="mt-3 text-sm text-red-400">
                Required checks failed — live cannot be enabled until they pass.
              </p>
            )}
            {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

            <label className="mt-4 flex items-center gap-2 text-sm text-gray-200">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                disabled={!report?.ready}
              />
              I understand this enables real trading.
            </label>

            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setShowModal(false)}
                className="rounded-md border border-white/10 px-4 py-2 text-sm text-gray-200 hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={confirmLive}
                disabled={!report?.ready || !confirmed || busy}
                className="rounded-md bg-hades-accent px-4 py-2 text-sm font-semibold text-black disabled:opacity-40"
              >
                Enable Live
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
