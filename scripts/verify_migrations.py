from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from nexus_core.models.orm import Base


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "services/api/alembic.ini"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"Expected exactly one Alembic head, found {heads}")

    tables = sorted(Base.metadata.tables)
    if not tables:
        raise SystemExit("ORM metadata did not load any tables")

    print(f"Alembic head: {heads[0]}")
    print(f"ORM tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()
