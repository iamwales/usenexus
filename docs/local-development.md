# Local Development

This guide is for running Nexus on a developer machine.

## Prerequisites

- Docker Desktop or another Docker daemon
- Python 3.12
- uv

## First Run

```bash
cp -n .env.example .env
uv sync --all-packages
docker compose up -d
docker compose exec api uv run alembic -c services/api/alembic.ini upgrade head
uv run python scripts/smoke_local.py
```

The API should be available at `http://localhost:8000`.

## Useful Commands

```bash
make dev
make smoke
make test-unit
make lint
make stop
```

## Local Defaults

`docker-compose.yml` includes safe development defaults, so `docker compose config`
works even before `.env` exists. Real provider keys should still be set in `.env`
before OAuth or model-backed query flows are tested.

Inside Docker, service URLs point at Compose service names:

- Postgres: `postgres:5432`
- Redis: `redis:6379`
- Redpanda: `redpanda:29092`
- Qdrant: `qdrant:6333`
- Elasticsearch: `elasticsearch:9200`

From the host machine, use the exposed localhost ports shown in
`docker-compose.yml`.

## Smoke Checks

The smoke script checks HTTP or TCP reachability for:

- API
- Postgres
- Redis
- Redpanda Kafka and admin API
- Qdrant
- Elasticsearch

If Docker is not running, `docker compose build` and `docker compose up` will fail
with a daemon socket error. Start Docker Desktop and retry the command.
