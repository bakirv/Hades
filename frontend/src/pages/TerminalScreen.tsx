// The single view of the platform's log stream.
//
// This screen and the old Logs screen consumed the same `useTerminal()` stream
// and rendered it through the same `LogLine`; Logs differed only by a minimum
// level filter. Two sidebar entries for one stream is a choice the operator has
// to make for no benefit, so the filter moved here and Logs is gone.

import { useEffect, useMemo, useRef, useState } from "react";
import { type LogRecord } from "../api/client";
import { useTerminal } from "../hooks";
import { Badge, PageHeader } from "../ui";

const LEVEL_COLORS: Record<string, string> = {
  debug: "text-gray-500",
  info: "text-sky-300",
  warning: "text-amber-300",
  error: "text-red-400",
  critical: "text-red-500",
};

export function LogLine({ record }: { record: LogRecord }) {
  const color = LEVEL_COLORS[record.level ?? "info"] ?? "text-gray-300";
  const extras = Object.entries(record)
    .filter(([k]) => !["event", "level", "logger", "timestamp"].includes(k))
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(" ");
  return (
    <div className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      <span className="text-hades-muted">{record.timestamp?.slice(11, 23)}</span>{" "}
      <span className={color}>{(record.level ?? "info").toUpperCase().padEnd(5)}</span>{" "}
      <span className="text-hades-muted">[{record.logger ?? "-"}]</span>{" "}
      <span className="text-gray-200">{record.event}</span>{" "}
      <span className="text-hades-muted">{extras}</span>
    </div>
  );
}

const LEVELS = ["all", "info", "warning", "error"] as const;
const RANK: Record<string, number> = { debug: 0, info: 1, warning: 2, error: 3, critical: 4 };

export function TerminalScreen() {
  const { lines, connected } = useTerminal();
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("all");
  const endRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (level === "all") return lines;
    const min = RANK[level];
    return lines.filter((r) => (RANK[r.level ?? "info"] ?? 1) >= min);
  }, [lines, level]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filtered]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <PageHeader title="Terminal" subtitle="Live platform log stream over WebSocket." />
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {LEVELS.map((l) => (
              <button
                key={l}
                onClick={() => setLevel(l)}
                className={`rounded-md px-3 py-1 text-xs transition-colors ${
                  level === l
                    ? "bg-hades-accent/10 text-hades-accent"
                    : "text-gray-400 hover:bg-white/5"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
          <Badge tone={connected ? "success" : "danger"}>
            {connected ? "connected" : "disconnected"}
          </Badge>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto rounded-xl border border-white/5 bg-black/50 p-4">
        {filtered.length === 0 && (
          <p className="text-sm text-hades-muted">
            {lines.length === 0 ? "Waiting for logs…" : `No ${level} lines yet.`}
          </p>
        )}
        {filtered.map((r, i) => (
          <LogLine key={i} record={r} />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
