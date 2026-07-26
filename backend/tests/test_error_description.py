"""Every logged failure must say something.

``str(exc)`` is empty for most of the exceptions this platform actually hits
under stress — connection timeouts, read timeouts, cancelled waits. Logging that
directly produced lines like ``rpc_call_failed ... error=`` during a real
incident, which told an operator that something failed and nothing else.
"""

from __future__ import annotations

import asyncio

import httpx

from hades.shared_kernel.errors import describe_exception


def test_a_timeout_with_no_message_is_named_by_its_class() -> None:
    # THE regression: these are raised with no arguments, so str() is "".
    assert str(httpx.ConnectTimeout("")) == ""
    assert describe_exception(httpx.ConnectTimeout("")) == "ConnectTimeout"


def test_every_common_silent_failure_produces_something_readable() -> None:
    for exc in (
        httpx.ConnectTimeout(""),
        httpx.ReadTimeout(""),
        httpx.ConnectError(""),
        TimeoutError(),
        asyncio.CancelledError(),
    ):
        assert describe_exception(exc).strip(), f"{type(exc).__name__} described as empty"


def test_a_message_is_kept_and_qualified_by_its_class() -> None:
    assert describe_exception(ValueError("bad mint")) == "ValueError: bad mint"


def test_a_message_that_already_names_the_class_is_not_repeated() -> None:
    # Nothing should ever read "ValueError: ValueError: ...".
    assert describe_exception(RuntimeError("RuntimeError: already said")) == (
        "RuntimeError: already said"
    )


def test_the_result_is_never_empty_for_any_exception() -> None:
    class _SilentError(Exception):
        def __str__(self) -> str:
            return "   "

    assert describe_exception(_SilentError()) == "_SilentError"
