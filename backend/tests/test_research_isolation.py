"""The Research Lab's isolation is *structural* — this test enforces it.

The whole safety argument rests on one fact: the lab has no path to execution.
We prove it by statically scanning every module in ``contexts/research`` and
asserting none imports the Execution, Risk or Portfolio contexts. If someone ever
wires such a dependency, this test fails before the code can ship — the lab must
never be able to place an order or enable live trading.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hades.contexts.research as research_pkg

_FORBIDDEN = (
    "hades.contexts.execution",
    "hades.contexts.risk",
    "hades.contexts.portfolio",
)


def _module_files() -> list[Path]:
    root = Path(research_pkg.__file__).parent
    return sorted(root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_research_context_never_imports_execution_risk_or_portfolio() -> None:
    offenders: list[str] = []
    for path in _module_files():
        for imported in _imports(path):
            if any(imported.startswith(f) for f in _FORBIDDEN):
                offenders.append(f"{path.name} imports {imported}")
    assert not offenders, (
        "Research Lab must not depend on trading contexts: " + "; ".join(offenders)
    )


def test_research_domain_events_are_facts_not_instructions() -> None:
    """Sanity: the promotion event carries a decision, never an order payload."""
    from hades.contexts.research.domain.events import StrategyPromoted
    from hades.contexts.research.domain.models import (
        CandidateKind,
        PromotionDecision,
        PromotionOutcome,
        ValidationStage,
    )
    from hades.shared_kernel.domain.identifiers import new_id

    decision = PromotionDecision(
        candidate_id=new_id(),
        candidate_name="x",
        kind=CandidateKind.STRATEGY,
        outcome=PromotionOutcome.APPROVED,
        stage=ValidationStage.SHADOW,
        manual_approved=True,
    )
    event = StrategyPromoted(aggregate_id=new_id(), decision=decision)
    payload = event.to_envelope()["payload"]
    # No order/size/mode fields — it is a governance fact only.
    assert "order" not in payload
    assert "size_usd" not in payload
    assert payload["decision"]["manual_approved"] is True
