import { Route, Routes } from "react-router-dom";
import { ModeSwitch } from "./components/ModeSwitch";
import { Sidebar } from "./components/Sidebar";
import { useLiveStatus } from "./hooks";
import { AIScreen } from "./pages/AIScreen";
import { ConfigScreen } from "./pages/ConfigScreen";
import { HealthScreen } from "./pages/HealthScreen";
import { IntelligenceScreen } from "./pages/IntelligenceScreen";
import { LogsScreen } from "./pages/LogsScreen";
import { PortfolioScreen } from "./pages/PortfolioScreen";
import { ResearchScreen } from "./pages/ResearchScreen";
import { RiskScreen } from "./pages/RiskScreen";
import { ScannerScreen } from "./pages/ScannerScreen";
import { SystemScreen } from "./pages/SystemScreen";
import { TerminalScreen } from "./pages/TerminalScreen";
import { TradingModeScreen } from "./pages/TradingModeScreen";

// Control-center shell: fixed sidebar, a header with the guarded Paper/Live
// switch and live status, and the routed screen area. Real per-screen data
// arrives in later phases — Phase 2 establishes the structure.
export default function App() {
  const status = useLiveStatus();

  return (
    <div className="flex h-screen overflow-hidden bg-hades-bg text-gray-100">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-white/5 px-6 py-3">
          <div className="text-sm text-hades-muted">
            {status ? (
              <span>
                v{status.version} · {status.environment} ·{" "}
                {status.event_bus_transport} · up {Math.floor(status.uptime_seconds)}s
              </span>
            ) : (
              <span className="text-red-400">API unreachable</span>
            )}
          </div>
          <ModeSwitch />
        </header>

        {status?.is_live && (
          <div className="bg-red-950/60 px-6 py-1.5 text-center text-xs font-semibold text-red-300">
            LIVE TRADING ENABLED — real orders are being placed
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<SystemScreen />} />
            <Route path="/trading" element={<TradingModeScreen />} />
            <Route path="/scanner" element={<ScannerScreen />} />
            <Route path="/intelligence" element={<IntelligenceScreen />} />
            <Route path="/portfolio" element={<PortfolioScreen />} />
            <Route path="/research" element={<ResearchScreen />} />
            <Route path="/risk" element={<RiskScreen />} />
            <Route path="/ai" element={<AIScreen />} />
            <Route path="/health" element={<HealthScreen />} />
            <Route path="/logs" element={<LogsScreen />} />
            <Route path="/terminal" element={<TerminalScreen />} />
            <Route path="/config" element={<ConfigScreen />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
