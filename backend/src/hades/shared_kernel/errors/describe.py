"""Turning an exception into something an operator can act on.

``str(exc)`` is the obvious way to log a failure and it has one bad habit: for a
large family of the exceptions this platform actually hits, it returns the empty
string. ``httpx.ConnectTimeout()``, ``httpx.ReadTimeout()``,
``asyncio.TimeoutError()`` and most connection errors are raised with no
arguments, so a perfectly reasonable ``error=str(exc)`` renders as::

    rpc_call_failed      endpoint=default method=getAccountInfo error=
    discovery_source_error source=dexscreener error=

which tells an operator that *something* failed and nothing else — not whether
the host was unreachable, whether it timed out, or whether it answered with an
error. That is the difference between a five-minute diagnosis and an hour of
guessing, and it shows up exactly when the platform is under stress and the logs
matter most.

:func:`describe_exception` falls back to the exception's class name when the
message is empty, so the same lines become::

    rpc_call_failed      endpoint=default method=getAccountInfo error=ConnectTimeout
    discovery_source_error source=dexscreener error=ReadTimeout
"""

from __future__ import annotations


def describe_exception(exc: BaseException) -> str:
    """A non-empty, human-readable description of ``exc``.

    Returns ``"<ClassName>: <message>"`` when the message adds something the
    class name does not, the class name alone when the message is empty, and the
    message alone when it already names the class (so nothing reads
    ``ValueError: ValueError``).
    """
    message = str(exc).strip()
    name = type(exc).__name__
    if not message:
        return name
    if message.startswith(name):
        return message
    return f"{name}: {message}"


__all__ = ["describe_exception"]
