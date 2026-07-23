// Left navigation. One entry per prepared screen. Kept text-only and minimal
// for speed and clarity (no icon library dependency).

import { NavLink } from "react-router-dom";

export interface NavItem {
  to: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "System" },
  { to: "/trading", label: "Trading Mode" },
  { to: "/scanner", label: "Scanner" },
  { to: "/intelligence", label: "Wallet Intel" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/research", label: "Research" },
  { to: "/risk", label: "Risk" },
  { to: "/ai", label: "AI" },
  { to: "/health", label: "Health" },
  { to: "/logs", label: "Logs" },
  { to: "/terminal", label: "Terminal" },
  { to: "/config", label: "Configuration" },
];

export function Sidebar() {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-white/5 bg-black/30">
      <div className="px-5 py-6">
        <span className="text-xl font-bold tracking-tight text-hades-accent">HADES</span>
        <p className="mt-1 text-[10px] uppercase tracking-widest text-hades-muted">
          Control Center
        </p>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `block rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-hades-accent/10 text-hades-accent"
                  : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
