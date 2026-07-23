"""The Audit System records consequential events and survives store failures."""

from __future__ import annotations

from hades.contexts.audit.application.query import AuditQueryService
from hades.contexts.audit.application.recorder import AuditRecorder
from hades.contexts.audit.application.subscriber import AuditSubscriber
from hades.contexts.audit.domain.models import AuditEntry, AuditQuery
from hades.contexts.audit.domain.ports import AuditStore
from hades.contexts.audit.infrastructure.store import InMemoryAuditStore
from hades.contexts.risk.domain.events import KillSwitchReset
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import InMemoryEventBus


async def test_recorder_writes_entry() -> None:
    store = InMemoryAuditStore()
    recorder = AuditRecorder(store)
    await recorder.log(actor="tester", action="did_thing", entity_type="platform")
    assert len(store.entries) == 1
    assert store.entries[0].action == "did_thing"


class _ExplodingStore(AuditStore):
    async def append(self, entry: AuditEntry) -> None:
        raise RuntimeError("db down")

    async def query(self, spec: AuditQuery) -> list[AuditEntry]:
        return []


async def test_recorder_swallows_store_failure() -> None:
    # A failed audit must never propagate to the audited action.
    recorder = AuditRecorder(_ExplodingStore())
    await recorder.log(actor="x", action="y")  # must not raise


async def test_subscriber_records_published_event() -> None:
    store = InMemoryAuditStore()
    subscriber = AuditSubscriber(AuditRecorder(store))
    bus = InMemoryEventBus()
    subscriber.register(bus)

    await bus.publish(KillSwitchReset(aggregate_id=new_id(), reason="test reset"))

    assert len(store.entries) == 1
    entry = store.entries[0]
    assert entry.action == "kill_switch_reset"
    assert entry.entity_type == "risk_manager"
    assert entry.after is not None and entry.after.get("reason") == "test reset"


async def test_query_filters_by_action() -> None:
    store = InMemoryAuditStore()
    await store.append(AuditEntry(actor="a", action="promote"))
    await store.append(AuditEntry(actor="b", action="reject"))
    service = AuditQueryService(store)

    results = await service.search(AuditQuery(action="promote"))
    assert len(results) == 1
    assert results[0].action == "promote"
