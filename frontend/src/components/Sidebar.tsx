// Left navigation: one entry per section, not per screen. Kept text-only and
// minimal for speed and clarity (no icon library dependency).
//
// A section stays highlighted while any of its tabs is open, so the sidebar
// still answers "where am I" even though the screen is one level deeper.

import { NavLink, useLocation } from "react-router-dom";
import { NAV_SECTIONS, sectionFor } from "../navigation";

export function Sidebar() {
  const { pathname } = useLocation();
  const active = sectionFor(pathname);

  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-white/5 bg-black/30">
      <div className="px-5 py-6">
        <span className="text-xl font-bold tracking-tight text-hades-accent">HADES</span>
        <p className="mt-1 text-[10px] uppercase tracking-widest text-hades-muted">
          Control Center
        </p>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV_SECTIONS.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            className={`block rounded-md px-3 py-2 text-sm transition-colors ${
              active?.to === section.to
                ? "bg-hades-accent/10 text-hades-accent"
                : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
            }`}
          >
            {section.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
