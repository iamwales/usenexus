from __future__ import annotations

import asyncio
import hashlib
import secrets

from nexus_core.database import get_db_session
from nexus_core.models.orm import ApiKey, Organization
from sqlalchemy import select


async def main() -> None:
    async with get_db_session() as session:
        org = await session.scalar(select(Organization).where(Organization.slug == "nexus-local"))
        if org is None:
            org = Organization(name="Nexus Local", slug="nexus-local", plan="starter")
            session.add(org)
            await session.flush()

        existing_key = await session.scalar(
            select(ApiKey).where(
                ApiKey.org_id == org.id,
                ApiKey.name == "Local Development",
                ApiKey.revoked_at.is_(None),
            )
        )
        if existing_key is not None:
            print(f"Organization: {org.id}")
            print(f"Existing key prefix: {existing_key.key_prefix}")
            return

        raw_key = "nxs_live_" + secrets.token_urlsafe(32)
        api_key = ApiKey(
            org_id=org.id,
            name="Local Development",
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            key_prefix=raw_key[:12],
            scopes=["query", "manage"],
            rate_limit_rpm=600,
        )
        session.add(api_key)
        await session.flush()

        print(f"Organization: {org.id}")
        print(f"API key: {raw_key}")


if __name__ == "__main__":
    asyncio.run(main())
