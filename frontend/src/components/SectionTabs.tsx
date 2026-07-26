// The tab bar for the current section. Renders nothing for a section that is a
// single screen, so the Terminal keeps its full height.

import { NavLink, useLocation } from "react-router-dom";
import { sectionFor } from "../navigation";

export function SectionTabs() {
  const { pathname } = useLocation();
  const section = sectionFor(pathname);
  if (!section || section.tabs.length < 2) return null;

  return (
    <div className="mb-6 flex gap-1 border-b border-white/5">
      {section.tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={`-mb-px border-b-2 px-4 py-2 text-sm transition-colors ${
            tab.to === pathname
              ? "border-hades-accent text-hades-accent"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  );
}
