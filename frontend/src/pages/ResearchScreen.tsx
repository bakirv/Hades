import { PageHeader, Panel, Placeholder } from "../ui";

export function ResearchScreen() {
  return (
    <div>
      <PageHeader
        title="Research"
        subtitle="Offline R&D on copied data — no path to execution."
      />
      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Research jobs">
          <Placeholder note="The Research Lab is not built in this phase." />
        </Panel>
        <Panel title="Experiments">
          <Placeholder note="Experiments and candidates will appear here." />
        </Panel>
      </div>
    </div>
  );
}
