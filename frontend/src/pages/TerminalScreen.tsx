import { useEffect, useRef } from "react";
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

export function TerminalScreen() {
  const { lines, connected } = useTerminal();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <PageHeader title="Terminal" subtitle="Live platform log stream over WebSocket." />
        <Badge tone={connected ? "success" : "danger"}>
          {connected ? "connected" : "disconnected"}
        </Badge>
      </div>
      <div className="flex-1 overflow-y-auto rounded-xl border border-white/5 bg-black/50 p-4">
        {lines.length === 0 && <p className="text-sm text-hades-muted">Waiting for logs…</p>}
        {lines.map((r, i) => (
          <LogLine key={i} record={r} />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
