"""Container healthcheck — invoked by Docker's ``healthcheck`` directive.

Two modes:

- **HTTP** (default, the API): exits 0 if ``/health`` answers with a non-unhealthy
  status. Run as ``python -m hades.ops.healthcheck``.
- **Liveness file** (background services): exits 0 if the role's liveness file was
  touched within ``--max-age`` seconds. Run as
  ``python -m hades.ops.healthcheck --role watchdog``.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from hades.ops.liveness import Liveness
from hades.shared_kernel.config import get_settings


def _check_http() -> int:
    settings = get_settings()
    url = f"http://127.0.0.1:{settings.api.port}/health"
    try:
        resp = httpx.get(url, timeout=5.0)
    except httpx.HTTPError:
        return 1
    if resp.status_code != 200:
        return 1
    return 0 if resp.json().get("status") != "unhealthy" else 1


def _check_liveness(role: str, max_age: float) -> int:
    settings = get_settings()
    liveness = Liveness(role, directory=settings.watchdog.liveness_dir)
    return 0 if liveness.is_fresh(max_age) else 1


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Hades container healthcheck")
    parser.add_argument("--role", default=None, help="background service role (liveness mode)")
    parser.add_argument(
        "--max-age",
        type=float,
        default=float(settings.watchdog.liveness_max_age_seconds),
        help="max liveness file age in seconds",
    )
    args = parser.parse_args()

    if args.role:
        return _check_liveness(args.role, args.max_age)
    return _check_http()


if __name__ == "__main__":
    sys.exit(main())
