"""The Retry Engine bounds attempts, backs off, and never masks hard failures."""

from __future__ import annotations

import pytest

from hades.contexts.execution.application.retry import (
    RetryableError,
    RetryEngine,
    RetryPolicy,
)


def _fast_policy(max_attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(max_attempts=max_attempts, base_delay_seconds=0.0, jitter=False)


async def test_succeeds_on_first_attempt() -> None:
    calls: list[int] = []

    async def op(attempt: int) -> str:
        calls.append(attempt)
        return "ok"

    result = await RetryEngine(_fast_policy()).run(op)
    assert result == "ok"
    assert calls == [1]


async def test_retries_until_success() -> None:
    calls: list[int] = []

    async def op(attempt: int) -> str:
        calls.append(attempt)
        if attempt < 3:
            raise RetryableError("transient")
        return "recovered"

    result = await RetryEngine(_fast_policy()).run(op)
    assert result == "recovered"
    assert calls == [1, 2, 3]


async def test_exhausts_attempts_then_raises() -> None:
    async def op(attempt: int) -> str:
        raise RetryableError("always fails")

    with pytest.raises(RetryableError, match="after 3 attempts"):
        await RetryEngine(_fast_policy()).run(op)


async def test_non_retryable_error_propagates_immediately() -> None:
    calls: list[int] = []

    async def op(attempt: int) -> str:
        calls.append(attempt)
        raise ValueError("hard failure")

    with pytest.raises(ValueError, match="hard failure"):
        await RetryEngine(_fast_policy()).run(op)
    assert calls == [1]  # never retried


def test_backoff_grows_and_is_capped() -> None:
    policy = RetryPolicy(
        max_attempts=6, base_delay_seconds=1.0, max_delay_seconds=8.0,
        backoff_multiplier=2.0, jitter=False,
    )
    assert policy.delay_for(1) == 0.0
    assert policy.delay_for(2) == 1.0
    assert policy.delay_for(3) == 2.0
    assert policy.delay_for(4) == 4.0
    assert policy.delay_for(10) == 8.0  # capped
