// The shape of the control center: four sections, each with its own tabs.
//
// It used to be twelve flat sidebar entries, several of which were views of the
// same thing — Risk rendered `config.risk`, which Configuration already showed
// in full, and Logs re-rendered the Terminal's stream with a level filter. A
// sidebar that long makes the operator scan it; grouping by *what you are doing*
// (watching the platform, researching, configuring, reading the stream) keeps
// every screen one or two clicks away without the noise.
//
// Every original URL still resolves, so bookmarks and links from the docs keep
// working — only where a screen *appears* changed.

export interface NavTab {
  to: string;
  label: string;
}

export interface NavSection {
  /** Where the sidebar entry points — always the section's first tab. */
  to: string;
  label: string;
  /** Empty when the section is a single screen and needs no tab bar. */
  tabs: NavTab[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    to: "/",
    label: "System",
    // The platform's own state: is it alive, and what is the book doing.
    // Health has no tab of its own — the Overview's health panel *was* the
    // Health screen, probe for probe, so keeping both was showing one thing
    // twice. /health still redirects here.
    tabs: [
      { to: "/", label: "Overview" },
      { to: "/portfolio", label: "Portfolio" },
    ],
  },
  {
    to: "/research",
    label: "Research",
    // Everything that produces knowledge rather than acting on it: what the
    // scanner found, what the wallet graph knows, what the committee believes.
    tabs: [
      { to: "/research", label: "Lab" },
      { to: "/scanner", label: "Scanner" },
      { to: "/intelligence", label: "Wallet Intel" },
      { to: "/ai", label: "AI" },
    ],
  },
  {
    to: "/config",
    label: "Configuration",
    // The knobs — including the two that used to be their own sections. Risk is
    // configured limits, and Trading Mode is the single most consequential
    // setting in the platform; both belong where settings live.
    tabs: [
      { to: "/config", label: "Settings" },
      { to: "/risk", label: "Risk" },
      { to: "/trading", label: "Trading Mode" },
    ],
  },
  {
    to: "/terminal",
    label: "Terminal",
    tabs: [],
  },
];

/** The section a path belongs to, for sidebar highlighting and the tab bar. */
export function sectionFor(pathname: string): NavSection | undefined {
  return (
    NAV_SECTIONS.find((section) =>
      section.tabs.length
        ? section.tabs.some((tab) => tab.to === pathname)
        : section.to === pathname,
    ) ?? NAV_SECTIONS.find((section) => section.to === pathname)
  );
}
