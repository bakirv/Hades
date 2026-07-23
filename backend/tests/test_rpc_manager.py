"""RPC Manager: routing, failover, health scoring, rate limiting, switches."""

from __future__ import annotations

from typing import Any

import pytest

from hades.shared_kernel.config.settings import RpcEndpointConfig, RpcSettings
from hades.shared_kernel.solana.rpc_manager import (
    RpcManager,
    RpcSwitch,
    RpcUnavailableError,
)


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeTransport:
    """Maps url -> dict result or Exception to raise."""

    def __init__(self, behavior: dict[str, Any]) -> None:
        self.behavior = behavior
        self.calls: list[str] = []

    async def send(self, url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        self.calls.append(url)
        outcome = self.behavior[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings(**kwargs: Any) -> RpcSettings:
    base = {
        "unhealthy_after_failures": 1,
        "recovery_probe_seconds": 100.0,
        "max_attempts": 5,
        "request_timeout_seconds": 5.0,
    }
    base.update(kwargs)
    return RpcSettings(**base)


def _endpoints() -> list[RpcEndpointConfig]:
    return [
        RpcEndpointConfig(name="a", http_url="http://a", priority=10),
        RpcEndpointConfig(name="b", http_url="http://b", priority=20),
    ]


async def test_routes_to_highest_priority_first() -> None:
    transport = FakeTransport({"http://a": {"result": 1}, "http://b": {"result": 2}})
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    result = await mgr.call("getX")
    assert result == 1
    assert mgr.active_endpoint == "a"
    assert transport.calls == ["http://a"]


async def test_fails_over_to_next_provider() -> None:
    transport = FakeTransport(
        {"http://a": RuntimeError("boom"), "http://b": {"result": 2}}
    )
    switches: list[RpcSwitch] = []

    async def on_switch(s: RpcSwitch) -> None:
        switches.append(s)

    mgr = RpcManager(
        _endpoints(),
        transport=transport,
        settings=_settings(),
        on_switch=on_switch,
        clock=FakeClock(),
    )
    result = await mgr.call("getX")
    assert result == 2
    assert mgr.active_endpoint == "b"
    assert transport.calls == ["http://a", "http://b"]
    assert switches and switches[-1].current == "b"


async def test_unhealthy_provider_is_parked() -> None:
    transport = FakeTransport(
        {"http://a": RuntimeError("boom"), "http://b": {"result": 2}}
    )
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    await mgr.call("getX")  # a fails -> parked, b serves
    transport.calls.clear()
    await mgr.call("getY")  # a is parked, so only b is tried
    assert transport.calls == ["http://b"]


async def test_all_providers_failing_raises() -> None:
    transport = FakeTransport(
        {"http://a": RuntimeError("x"), "http://b": RuntimeError("y")}
    )
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    with pytest.raises(RpcUnavailableError):
        await mgr.call("getX")


async def test_jsonrpc_error_is_a_failure() -> None:
    transport = FakeTransport(
        {"http://a": {"error": {"code": -32000}}, "http://b": {"result": 9}}
    )
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    assert await mgr.call("getX") == 9


async def test_rate_limit_skips_to_other_provider() -> None:
    clock = FakeClock()
    transport = FakeTransport({"http://a": {"result": 1}, "http://b": {"result": 2}})
    endpoints = [
        RpcEndpointConfig(name="a", http_url="http://a", priority=10, rate_limit_per_second=1),
        RpcEndpointConfig(name="b", http_url="http://b", priority=20, rate_limit_per_second=1),
    ]
    mgr = RpcManager(endpoints, transport=transport, settings=_settings(), clock=clock)
    assert await mgr.call("g") == 1  # a (1/1 used this second)
    assert await mgr.call("g") == 2  # a throttled -> b
    # Both throttled now within the same second -> unavailable.
    with pytest.raises(RpcUnavailableError):
        await mgr.call("g")
    # New second resets the windows.
    clock.t += 1
    assert await mgr.call("g") == 1


async def test_health_check_uses_call() -> None:
    transport = FakeTransport({"http://a": {"result": "ok"}, "http://b": {"result": "ok"}})
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    assert await mgr.health_check() is True


async def test_endpoints_snapshot_shape() -> None:
    transport = FakeTransport({"http://a": {"result": 1}, "http://b": {"result": 2}})
    mgr = RpcManager(_endpoints(), transport=transport, settings=_settings(), clock=FakeClock())
    await mgr.call("g")
    snap = mgr.endpoints()
    assert {e["name"] for e in snap} == {"a", "b"}
    assert all("health_score" in e and "latency_ms" in e for e in snap)
