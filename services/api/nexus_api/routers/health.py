from fastapi import APIRouter, Request
from nexus_core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0", "environment": settings.environment}


@router.get("/health/deep")
async def health_deep(request: Request) -> dict:
    """Check all downstream dependencies."""
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        from nexus_core.database import engine

        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Redis
    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Qdrant
    try:
        qdrant = request.app.state.qdrant
        await qdrant.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    # Elasticsearch
    try:
        es = request.app.state.es
        info = await es.ping()
        checks["elasticsearch"] = "ok" if info else "unreachable"
    except Exception as e:
        checks["elasticsearch"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }
