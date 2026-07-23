import { PageHeader, Panel, Placeholder } from "../ui";

export function PortfolioScreen() {
  return (
    <div>
      <PageHeader title="Portfolio" subtitle="Positions, exposure and PnL." />
      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Open positions">
          <Placeholder note="No positions — trading logic arrives in a later phase." />
        </Panel>
        <Panel title="Equity curve">
          <Placeholder note="Equity series will render here once trading is live-tracked." />
        </Panel>
      </div>
    </div>
  );
}
