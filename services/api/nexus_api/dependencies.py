from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request

from nexus_api.errors import api_error

ScopeDependency = Callable[[Request], Coroutine[Any, Any, None]]


def require_scopes(*required_scopes: str) -> ScopeDependency:
    async def dependency(request: Request) -> None:
        granted = set(getattr(request.state, "scopes", []) or [])
        if "manage" in granted or set(required_scopes).issubset(granted):
            return

        raise api_error(
            403,
            "insufficient_scope",
            "API key does not have the required scope",
            details={
                "required": list(required_scopes),
                "granted": sorted(granted),
            },
        )

    return dependency
