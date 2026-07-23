import { useEffect, useState } from "react";
import {
  api,
  type IntelCluster,
  type IntelligenceStatus,
  type WalletProfile,
  type WalletRelationship,
  type WalletTimelineEntry,
} from "../api/client";
import { Badge, PageHeader, Panel, Row, StatusDot } from "../ui";

// Wallet Intelligence — the on-chain knowledge base. Read-only: it only shows
// what the platform knows about wallets (score, reputation, behaviour, funding,
// clusters, timeline). It never trades and takes no decision.

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/20 p-4">
      <div className="text-xs uppercase tracking-wide text-hades-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-gray-100">{value}</div>
    </div>
  );
}

const BAND_TONE: Record<string, "neutral" | "danger" | "success" | "warn"> = {
  smart_money: "success",
  trusted: "success",
  neutral: "neutral",
  risky: "warn",
  dumb_money: "warn",
  scammer: "danger",
};

function shortAddr(addr: string): string {
  return addr.length > 12 ? `${addr.slice(0, 4)}…${addr.slice(-4)}` : addr;
}

// A labelled 0–100 bar. `invert` flips the colour meaning for risk (high = bad).
function Bar({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  const good = invert ? value < 50 : value >= 50;
  const color = invert
    ? value >= 65
      ? "bg-red-500"
      : value >= 45
        ? "bg-amber-500"
        : "bg-emerald-500"
    : good
      ? "bg-emerald-500"
      : value >= 35
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <div className="py-1.5">
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-hades-muted">{label}</span>
        <span className="text-gray-300">{value.toFixed(0)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div className={`h-full ${color}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

function ScoreDial({ score, band }: { score: number; band: string }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-hades-accent/30">
        <span className="text-2xl font-bold text-gray-100">{score.toFixed(0)}</span>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-hades-muted">Wallet Score</div>
        <div className="mt-1">
          <Badge tone={BAND_TONE[band] ?? "neutral"}>{band.replace(/_/g, " ")}</Badge>
        </div>
      </div>
    </div>
  );
}

function WalletDetail({
  profile,
  timeline,
  relationships,
}: {
  profile: WalletProfile;
  timeline: WalletTimelineEntry[];
  relationships: WalletRelationship[];
}) {
  const rep = profile.reputation;
  return (
    <div className="space-y-6">
      <Panel title={`Profile · ${shortAddr(profile.address)} · v${profile.version}`}>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <ScoreDial score={profile.wallet_score} band={profile.band} />
            <div className="flex flex-wrap gap-2">
              <Badge tone={profile.money_class === "smart" ? "success" : profile.money_class === "dumb" ? "warn" : "neutral"}>
                {profile.money_class} money
              </Badge>
              <Badge>{profile.behavior} · {(profile.behavior_confidence * 100).toFixed(0)}%</Badge>
              <Badge>influence {profile.influence.toFixed(0)}</Badge>
              <Badge>smart {profile.smart_money_score.toFixed(0)}</Badge>
              {profile.cluster_id && <Badge tone="warn">cluster {profile.cluster_id.slice(0, 10)}</Badge>}
            </div>
          </div>
          <div>
            <Bar label="Trust" value={rep.trust} />
            <Bar label="Risk" value={rep.risk} invert />
            <Bar label="Consistency" value={rep.consistency} />
            <Bar label="Experience" value={rep.experience} />
            <Bar label="Profitability" value={rep.profitability} />
          </div>
        </div>
      </Panel>

      {profile.explanation && (
        <Panel title="Why this score">
          <p className="mb-3 text-sm text-gray-300">{profile.explanation.summary}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <ul className="space-y-1">
              {profile.explanation.positives.map((p, i) => (
                <li key={i} className="text-sm text-emerald-300">+ {p}</li>
              ))}
              {profile.explanation.positives.length === 0 && (
                <li className="text-sm text-hades-muted">No positive signals yet.</li>
              )}
            </ul>
            <ul className="space-y-1">
              {profile.explanation.negatives.map((n, i) => (
                <li key={i} className="text-sm text-red-300">− {n}</li>
              ))}
              {profile.explanation.negatives.length === 0 && (
                <li className="text-sm text-hades-muted">No negative signals.</li>
              )}
            </ul>
          </div>
        </Panel>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Activity">
          <Row label="First seen" value={fmt(profile.first_seen_at)} />
          <Row label="Last active" value={fmt(profile.last_active_at)} />
          <Row label="Observations" value={profile.observations} />
          <Row label="Tokens traded" value={profile.tokens_traded} />
          <Row label="Launches" value={profile.launches} />
          <Row label="Rugs participated" value={profile.rugs_participated} danger={profile.rugs_participated > 0} />
          <Row label="Successes" value={profile.successes} />
          <Row label="Avg supply %" value={profile.avg_pct_supply.toFixed(2)} />
          <Row label="DEXes" value={profile.dexes.join(", ") || "—"} />
          <Row label="Roles" value={profile.roles.join(", ") || "—"} />
        </Panel>

        <Panel title="Funding lineage">
          {profile.funding.length === 0 && <p className="text-sm text-hades-muted">No funding edges recorded.</p>}
          {profile.funding.map((f) => (
            <Row
              key={f.source}
              label={shortAddr(f.source)}
              value={
                <Badge tone={f.kind === "mixer" || f.kind === "suspicious" ? "danger" : f.kind === "exchange" ? "success" : "neutral"}>
                  {f.kind}
                </Badge>
              }
            />
          ))}
        </Panel>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Timeline">
          {timeline.length === 0 && <p className="text-sm text-hades-muted">No timeline events.</p>}
          {timeline.map((t, i) => (
            <Row
              key={i}
              label={fmt(t.at)}
              value={
                <span className="text-gray-300">
                  {t.kind}
                  {t.mint ? ` · ${shortAddr(t.mint)}` : ""}
                </span>
              }
            />
          ))}
        </Panel>

        <Panel title="Relationships">
          {relationships.length === 0 && <p className="text-sm text-hades-muted">No graph edges.</p>}
          {relationships.map((r, i) => (
            <Row
              key={i}
              label={`${shortAddr(r.source)} → ${shortAddr(r.target)}`}
              value={<span className="text-gray-300">{r.kind} · w{r.weight.toFixed(1)}</span>}
            />
          ))}
        </Panel>
      </div>
    </div>
  );
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export function IntelligenceScreen() {
  const [status, setStatus] = useState<IntelligenceStatus | null>(null);
  const [clusters, setClusters] = useState<IntelCluster[]>([]);
  const [leaders, setLeaders] = useState<WalletProfile[]>([]);
  const [query, setQuery] = useState("");
  const [profile, setProfile] = useState<WalletProfile | null>(null);
  const [timeline, setTimeline] = useState<WalletTimelineEntry[]>([]);
  const [relationships, setRelationships] = useState<WalletRelationship[]>([]);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = () => {
      api.intelligenceStatus().then(setStatus).catch(() => undefined);
      api.intelligenceClusters().then((r) => setClusters(r.clusters)).catch(() => undefined);
      api.smartMoney().then((r) => setLeaders(r.wallets)).catch(() => undefined);
    };
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const lookup = async (address: string) => {
    const addr = address.trim();
    if (!addr) return;
    setLoading(true);
    setLookupError(null);
    setProfile(null);
    try {
      const p = await api.walletProfile(addr);
      const [tl, rel] = await Promise.all([
        api.walletTimeline(addr).then((r) => r.timeline).catch(() => []),
        api.walletRelationships(addr).then((r) => r.relationships).catch(() => []),
      ]);
      setProfile(p);
      setTimeline(tl);
      setRelationships(rel);
    } catch (err) {
      setLookupError(
        err instanceof Error && err.message.includes("404")
          ? "No profile for this wallet yet — it has not been observed."
          : "Lookup failed (is the API reachable and the wallet known?).",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Wallet Intelligence"
        subtitle="On-chain knowledge base — it only knows. It never trades or decides."
      />

      <div className="flex items-center gap-2">
        <StatusDot status={status?.running ? "healthy" : status?.enabled ? "degraded" : "unknown"} />
        <span className="text-sm text-gray-200">
          {status?.running ? "Running" : status?.enabled ? "Enabled (starting)" : "Disabled"}
        </span>
        {status?.live?.live_lookups && <Badge tone="success">live lookups</Badge>}
        {status?.live?.rpc_active && <Badge>RPC: {status.live.rpc_active}</Badge>}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Wallets known" value={status?.wallets_total ?? 0} />
        <Stat label="Smart money" value={status?.smart_money_total ?? 0} />
        <Stat label="Clusters" value={status?.clusters_total ?? 0} />
        <Stat label="New (session)" value={status?.live?.wallets_registered_session ?? 0} />
      </div>

      <Panel title="Wallet lookup">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void lookup(query);
          }}
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Wallet address (base58)"
            className="flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-gray-100 outline-none focus:border-hades-accent/50"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-hades-accent/20 px-4 py-2 text-sm font-medium text-hades-accent hover:bg-hades-accent/30 disabled:opacity-50"
          >
            {loading ? "Looking…" : "Look up"}
          </button>
        </form>
        {lookupError && <p className="mt-3 text-sm text-amber-300">{lookupError}</p>}
      </Panel>

      {profile && (
        <WalletDetail profile={profile} timeline={timeline} relationships={relationships} />
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Smart-money leaderboard">
          {leaders.length === 0 && <p className="text-sm text-hades-muted">No smart-money wallets yet.</p>}
          {leaders.map((w) => (
            <Row
              key={w.address}
              label={
                <button className="text-left hover:text-hades-accent" onClick={() => { setQuery(w.address); void lookup(w.address); }}>
                  {shortAddr(w.address)}
                </button>
              }
              value={
                <span className="flex items-center gap-2">
                  <Badge tone={BAND_TONE[w.band] ?? "neutral"}>{w.band.replace(/_/g, " ")}</Badge>
                  <span className="text-gray-300">{w.wallet_score.toFixed(0)}</span>
                </span>
              }
            />
          ))}
        </Panel>

        <Panel title="Recent clusters">
          {clusters.length === 0 && <p className="text-sm text-hades-muted">No clusters detected yet.</p>}
          {clusters.map((c) => (
            <Row
              key={c.cluster_id}
              label={c.cluster_id.slice(0, 12)}
              value={
                <span className="text-gray-300">
                  {c.member_count} wallets · {c.pct_supply.toFixed(1)}% · conf {(c.confidence * 100).toFixed(0)}%
                </span>
              }
            />
          ))}
        </Panel>
      </div>
    </div>
  );
}
