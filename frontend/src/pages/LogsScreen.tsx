import { useState } from "react";
import { useTerminal } from "../hooks";
import { PageHeader } from "../ui";
import { LogLine } from "./TerminalScreen";

const LEVELS = ["all", "info", "warning", "error"];

export function LogsScreen() {
  const { lines } = useTerminal();
  const [level, setLevel] = useState("all");

  const rank: Record<string, number> = { debug: 0, info: 1, warning: 2, error: 3, critical: 4 };
  const min = level === "all" ? -1 : rank[level];
  const filtered = lines.filter((r) => (rank[r.level ?? "info"] ?? 1) >= min);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <PageHeader title="Logs" subtitle="Structured logs, filterable by minimum level." />
        <div className="flex gap-1">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={`rounded-md px-3 py-1 text-xs ${
                level === l ? "bg-hades-accent/10 text-hades-accent" : "text-gray-400 hover:bg-white/5"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto rounded-xl border border-white/5 bg-black/50 p-4">
        {filtered.length === 0 && <p className="text-sm text-hades-muted">No matching logs.</p>}
        {filtered.map((r, i) => (
          <LogLine key={i} record={r} />
        ))}
      </div>
    </div>
  );
}
