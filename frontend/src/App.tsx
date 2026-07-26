import { Navigate, Route, Routes } from "react-router-dom";
import { ModeSwitch } from "./components/ModeSwitch";
import { SectionTabs } from "./components/SectionTabs";
import { Sidebar } from "./components/Sidebar";
import { useLiveStatus } from "./hooks";
import { AIScreen } from "./pages/AIScreen";
import { ConfigScreen } from "./pages/ConfigScreen";
import { IntelligenceScreen } from "./pages/IntelligenceScreen";
import { PortfolioScreen } from "./pages/PortfolioScreen";
import { ResearchScreen } from "./pages/ResearchScreen";
import { RiskScreen } from "./pages/RiskScreen";
import { ScannerScreen } from "./pages/ScannerScreen";
import { SystemScreen } from "./pages/SystemScreen";
import { TerminalScreen } from "./pages/TerminalScreen";
import { TradingModeScreen } from "./pages/TradingModeScreen";

// Control-center shell: fixed sidebar, a header with the guarded Paper/Live
// switch and live status, a tab bar for the active section, and the routed
// screen area.
//
// Screens are grouped into four sections (see `navigation.ts`) rather than
// listed flat. Every original path still routes to the same screen — only where
// it *appears* changed — so nothing that linked to /portfolio or /risk broke.
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

        <main className="flex flex-1 flex-col overflow-y-auto p-6">
          <SectionTabs />
          {/* min-h-0 lets the Terminal's h-full actually mean "the rest of the
              area" instead of overflowing past the tab bar. */}
          <div className="min-h-0 flex-1">
            <Routes>
              <Route path="/" element={<SystemScreen />} />
              <Route path="/portfolio" element={<PortfolioScreen />} />
              {/* Health folded into the Overview; keep the old link alive. */}
              <Route path="/health" element={<Navigate to="/" replace />} />

              <Route path="/research" element={<ResearchScreen />} />
              <Route path="/scanner" element={<ScannerScreen />} />
              <Route path="/intelligence" element={<IntelligenceScreen />} />
              <Route path="/ai" element={<AIScreen />} />

              <Route path="/config" element={<ConfigScreen />} />
              <Route path="/risk" element={<RiskScreen />} />
              <Route path="/trading" element={<TradingModeScreen />} />

              <Route path="/terminal" element={<TerminalScreen />} />
              {/* Logs merged into the Terminal; keep the old link alive. */}
              <Route path="/logs" element={<Navigate to="/terminal" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
