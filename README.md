# Nexus

**Connect everything. Know everything.**

Nexus is an open-core, MCP-native enterprise RAG platform. Connect your company's tools — Google Drive, Notion, ClickUp, Slack, Google Calendar, Confluence, GitHub, Linear — and query across all of them with a single API call. Answers are grounded, cited, always fresh, and permission-aware.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Connectors](#connectors)
- [Prerequisites](#prerequisites)
- [Quick Start (Local)](#quick-start-local)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## Overview

### What Nexus Does

- **Connects** to your company's tools via OAuth in under 3 minutes per integration
- **Indexes** all accessible content automatically — documents, tasks, messages, calendar events
- **Stays fresh** — content changes are reflected within 60 seconds (webhook) or 15 minutes (polling fallback)
- **Answers** natural language questions with citations linking back to exact source documents
- **Respects permissions** — users only retrieve content they can access in the source system

### How It Works

```
Your tools → MCP connectors → Ingestion pipeline → Vector + BM25 index → Query API → Cited answers
```

Each connector implements a standard MCP interface (`list_resources`, `fetch_resource`, `subscribe`). Content is chunked using connector-specific strategies, embedded with `text-embedding-3-large`, stored in Qdrant (dense) and Elasticsearch (sparse), and retrieved via hybrid search with reranking.

### Supported Connectors (v1)

| Connector | Content Indexed | Live Updates |
|---|---|---|
| Google Drive | Docs, Sheets, PDFs, Slides | Webhooks |
| Notion | Pages, Databases, Rows | Webhooks + Polling |
| ClickUp | Tasks, Docs, Comments | Webhooks |
| Slack | Messages, Threads, Files | Events API |
| Google Calendar | Events, Attendees | Webhooks |
| Confluence | Pages, Blog Posts | Webhooks |
| GitHub | Markdown docs, Issues, PRs | Webhooks |
| Linear | Issues, Projects, Comments | Webhooks |

---

## Architecture

```
services/
├── api/            FastAPI — REST + SSE streaming query API
├── ingestion/      Kafka consumer → chunk → embed → upsert
├── connectors/     MCP adapter framework + 8 connector implementations
├── scheduler/      Polling scheduler + webhook renewal jobs
└── worker/         Celery — bulk sync, re-index, cleanup jobs

packages/
├── core/           Shared models, config, logging, tracing
├── chunker/        Chunking strategies (parent-child, semantic, heading-aware)
└── retriever/      Hybrid search, RRF, reranking, HyDE, citation linking

infra/
├── terraform/      AWS infrastructure as code
├── k8s/            Kubernetes manifests
└── docker/         Docker Compose for local development
```

### Storage

| Store | Purpose |
|---|---|
| PostgreSQL 16 | Tenant registry, connections, document index, API keys, query logs |
| Qdrant | Dense vector storage — one collection per tenant |
| Elasticsearch 8 | Sparse BM25 index — one index per tenant |
| Redis 7 | Query cache, embedding cache, rate limiting, session store |
| S3/R2 | Raw file staging (48hr retention) |
| Kafka / Redpanda | Change event stream between connectors and ingestion pipeline |

---

## Connectors

All connectors implement `BaseConnector` from `packages/core/nexus_core/connectors/base.py`.

### Connector Lifecycle

```
1. OAuth flow (start → callback → token persisted)
2. Full sync (list_resources → fetch_resource → chunk → embed → upsert)
3. Webhook subscription (subscribe → connector registers Nexus webhook URL)
4. Incremental sync (webhook fires → parse_webhook → ChangeEvent → Kafka → ingest)
5. Polling fallback (scheduler polls every 15min when webhooks unavailable)
```

### Adding a New Connector

```python
# services/connectors/nexus_connectors/my_app/connector.py

from nexus_core.connectors.base import BaseConnector, ResourcePage, Resource, ChangeEvent

class MyAppConnector(BaseConnector):
    connector_id = "my_app"
    display_name = "My App"
    oauth_scopes = ["read:content"]

    async def list_resources(self, credentials, cursor=None) -> ResourcePage:
        ...

    async def fetch_resource(self, credentials, resource_id) -> Resource:
        ...

    async def subscribe(self, credentials, webhook_url) -> Subscription:
        ...

    async def parse_webhook(self, payload, headers) -> list[ChangeEvent]:
        ...

    async def check_permission(self, credentials, resource_id, user_email) -> bool:
        ...
```

Register in `services/connectors/nexus_connectors/registry.py`:

```python
CONNECTOR_REGISTRY = {
    ...
    "my_app": MyAppConnector,
}
```

---

## Prerequisites

- **Docker** 24+ and **Docker Compose** v2
- **Python** 3.12+
- **uv** 0.4+ (package manager)
- **Node.js** 20+ (dashboard only)
- API keys: OpenAI (embeddings), Cohere (reranker), Anthropic or OpenAI (generation)

---

## Quick Start (Local)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/nexus.git
cd nexus
cp .env.example .env
```

Fill in `.env`:

```bash
# Required
OPENAI_API_KEY=sk-...
COHERE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...    # or use OPENAI_API_KEY for generation

# Connector OAuth apps (create dev apps in each provider)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NOTION_CLIENT_ID=...
NOTION_CLIENT_SECRET=...
CLICKUP_CLIENT_ID=...
CLICKUP_CLIENT_SECRET=...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...
CONFLUENCE_CLIENT_ID=...
CONFLUENCE_CLIENT_SECRET=...
GITHUB_APP_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=./secrets/github-app.pem
LINEAR_CLIENT_ID=...
LINEAR_CLIENT_SECRET=...
```

### 2. Start the stack

```bash
docker compose up -d
```

This starts: PostgreSQL, Qdrant, Elasticsearch, Redpanda (Kafka), Redis, and all Nexus services.

### 3. Run database migrations

```bash
docker compose exec api uv run alembic upgrade head
```

### 4. Create your first tenant

```bash
curl -X POST http://localhost:8000/v1/internal/organizations \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "slug": "acme"}'

# Returns: { "org_id": "org_xxx", "api_key": "nxs_live_xxx" }
```

### 5. Connect Google Drive

```bash
# Get OAuth URL
curl http://localhost:8000/v1/connections/oauth/start?connector=google_drive \
  -H "Authorization: Bearer nxs_live_xxx"

# Returns: { "oauth_url": "https://accounts.google.com/..." }
# Open in browser, authorize, callback handled automatically
```

### 6. Trigger a sync and query

```bash
# Trigger full sync
curl -X POST http://localhost:8000/v1/connections/{connection_id}/sync \
  -H "Authorization: Bearer nxs_live_xxx"

# Watch sync status
curl http://localhost:8000/v1/connections/{connection_id}/status \
  -H "Authorization: Bearer nxs_live_xxx"

# Query when sync completes
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer nxs_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is our Q3 strategy?"}'
```

---

## Configuration

### Environment Variables

#### Core

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `KAFKA_BROKERS` | Yes | — | Comma-separated Kafka broker addresses |
| `QDRANT_URL` | Yes | — | Qdrant HTTP URL |
| `QDRANT_API_KEY` | No | — | Qdrant API key (cloud) |
| `ELASTICSEARCH_URL` | Yes | — | Elasticsearch URL |
| `ELASTICSEARCH_API_KEY` | No | — | ES API key |
| `S3_BUCKET` | Yes | — | Raw content staging bucket |
| `AWS_REGION` | No | `us-east-1` | AWS region |

#### AI / Models

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key (embeddings + optional generation) |
| `ANTHROPIC_API_KEY` | No | — | Anthropic key (preferred for generation) |
| `COHERE_API_KEY` | Yes | — | Cohere Rerank API key |
| `EMBEDDING_MODEL` | No | `text-embedding-3-large` | OpenAI embedding model |
| `GENERATION_MODEL` | No | `claude-sonnet-4-20250514` | LLM for answer generation |
| `EMBEDDING_DIMENSIONS` | No | `3072` | Vector dimensions |

#### Ingestion

| Variable | Required | Default | Description |
|---|---|---|---|
| `CHUNK_SIZE_TOKENS` | No | `512` | Default chunk size |
| `CHUNK_OVERLAP_TOKENS` | No | `64` | Overlap between chunks |
| `EMBEDDING_BATCH_SIZE` | No | `32` | Batch size for embedding calls |
| `MAX_INGEST_WORKERS` | No | `4` | Parallel ingestion workers |

#### Query

| Variable | Required | Default | Description |
|---|---|---|---|
| `RETRIEVAL_TOP_K` | No | `40` | Candidates per retrieval pass |
| `RERANK_TOP_K` | No | `20` | Candidates sent to reranker |
| `FINAL_TOP_K` | No | `8` | Context chunks sent to LLM |
| `QUERY_CACHE_TTL_SECONDS` | No | `300` | Query cache TTL |
| `HYDE_ENABLED` | No | `true` | Enable HyDE query expansion |

#### Security

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | Yes | — | JWT signing secret (min 32 chars) |
| `ENCRYPTION_KEY_ID` | Yes | — | AWS KMS key ID for OAuth token encryption |
| `WEBHOOK_SIGNING_SECRET` | Yes | — | Internal webhook validation secret |

---

## API Reference

Full API documentation: [https://docs.usenexus.ai](https://docs.usenexus.ai)

### Query

```http
POST /v1/query
Authorization: Bearer <api_key>
Content-Type: application/json

{
  "query": "string",
  "connectors": ["google_drive", "notion"],   // optional — default: all connected
  "top_k": 5,                                 // optional — default: 5, max: 20
  "stream": false,                            // optional — SSE streaming
  "user_email": "alice@company.com"           // optional — enables per-user ACL filtering
}
```

**Response:**

```json
{
  "answer": "Based on the Q3 strategy document...",
  "citations": [
    {
      "number": 1,
      "title": "Q3 Strategy — Final",
      "connector": "google_drive",
      "source_url": "https://docs.google.com/...",
      "excerpt": "We will focus on enterprise customers...",
      "author": "alice@company.com",
      "modified_at": "2025-05-15T14:00:00Z"
    }
  ],
  "latency_ms": 892,
  "cached": false
}
```

**Streaming (SSE):**

```http
POST /v1/query
{ "query": "...", "stream": true }

data: {"type": "token", "content": "Based "}
data: {"type": "token", "content": "on the "}
data: {"type": "citations", "citations": [...]}
data: {"type": "done", "latency_ms": 1100}
```

### Connections

```http
# List connections
GET /v1/connections

# Start OAuth flow
GET /v1/connections/oauth/start?connector=notion

# Check connection status
GET /v1/connections/{id}/status

# Trigger full re-sync
POST /v1/connections/{id}/sync

# Delete connection and all indexed data
DELETE /v1/connections/{id}
```

### Error Codes

| Code | Meaning |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Insufficient scope |
| `404` | Resource not found |
| `429` | Rate limit exceeded (check `Retry-After` header) |
| `422` | Validation error (check `errors` array in response) |
| `503` | Upstream dependency unavailable |

---

## Development

### Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all workspace dependencies
uv sync --all-packages

# Install pre-commit hooks
uv run pre-commit install
```

### Running Services Individually

```bash
# API
cd services/api && uv run uvicorn nexus_api.main:app --reload --port 8000

# Ingestion consumer
cd services/ingestion && uv run python -m nexus_ingestion.consumer

# Scheduler
cd services/scheduler && uv run python -m nexus_scheduler.main

# Celery worker
cd services/worker && uv run celery -A nexus_worker.celery_app worker --loglevel=info
```

### Code Quality

```bash
# Lint
uv run ruff check .

# Type check
uv run mypy .

# Format
uv run ruff format .

# All checks (runs in CI)
make lint
```

### Adding Alembic Migrations

```bash
cd services/api
uv run alembic revision --autogenerate -m "add my new table"
uv run alembic upgrade head
```

---

## Testing

### Unit Tests

```bash
uv run pytest packages/ services/ -v --ignore=tests/integration --ignore=tests/e2e
```

### Integration Tests (requires Docker)

```bash
docker compose -f docker-compose.test.yml up -d
uv run pytest tests/integration -v
docker compose -f docker-compose.test.yml down
```

### E2E Tests (requires staging credentials)

```bash
NEXUS_TEST_API_KEY=... NEXUS_TEST_BASE_URL=https://staging.usenexus.ai \
  uv run pytest tests/e2e -v
```

### RAG Evaluation (RAGAS)

```bash
# Run against golden dataset
uv run python evals/run_ragas.py \
  --dataset evals/golden/google_drive.json \
  --api-key nxs_live_xxx \
  --output evals/results/$(date +%Y%m%d).json
```

Target metrics:

| Metric | Minimum | Target |
|---|---|---|
| Faithfulness | 0.85 | 0.92 |
| Answer relevance | 0.80 | 0.88 |
| Context precision | 0.75 | 0.82 |
| Context recall | 0.70 | 0.78 |

---

## Deployment

### Prerequisites

- AWS account with EKS, RDS, ElastiCache, MSK, S3 provisioned via Terraform
- ECR repositories created for each service
- GitHub Actions secrets configured
- ArgoCD installed in EKS cluster

### Provision Infrastructure

```bash
cd infra/terraform
terraform init
terraform workspace new production
terraform plan -var-file=envs/production.tfvars
terraform apply -var-file=envs/production.tfvars
```

### Deploy to Staging

Automatic on every merge to `main`. ArgoCD watches `infra/k8s/staging/` and applies changes.

### Deploy to Production

```bash
# Tag a release
git tag v1.2.0
git push origin v1.2.0

# ArgoCD will show a pending sync in production — approve in the ArgoCD UI
# Or use CLI:
argocd app sync nexus-production
```

### Rollback

```bash
argocd app rollback nexus-production --revision <previous-revision>
```

### Health Checks

```bash
# API health
curl https://api.usenexus.ai/health

# Deep health (checks all dependencies)
curl https://api.usenexus.ai/health/deep
```

---

## Project Structure

```
nexus/
├── services/
│   ├── api/
│   │   ├── nexus_api/
│   │   │   ├── main.py             # FastAPI app factory
│   │   │   ├── routers/
│   │   │   │   ├── query.py        # POST /v1/query
│   │   │   │   ├── connections.py  # Connection management
│   │   │   │   ├── documents.py    # Document management
│   │   │   │   └── keys.py         # API key management
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py         # JWT + API key auth
│   │   │   │   ├── tenant.py       # Tenant context injection
│   │   │   │   └── rate_limit.py   # Redis-backed rate limiting
│   │   │   └── dependencies.py
│   │   ├── alembic/                # Database migrations
│   │   └── pyproject.toml
│   ├── ingestion/
│   │   ├── nexus_ingestion/
│   │   │   ├── consumer.py         # Kafka consumer main loop
│   │   │   ├── pipeline.py         # Dedup → chunk → embed → upsert
│   │   │   └── upsert.py           # Qdrant + ES upsert logic
│   │   └── pyproject.toml
│   ├── connectors/
│   │   ├── nexus_connectors/
│   │   │   ├── base.py             # BaseConnector ABC
│   │   │   ├── registry.py         # ConnectorRegistry
│   │   │   ├── google_drive/
│   │   │   ├── notion/
│   │   │   ├── clickup/
│   │   │   ├── slack/
│   │   │   ├── google_calendar/
│   │   │   ├── confluence/
│   │   │   ├── github/
│   │   │   └── linear/
│   │   └── pyproject.toml
│   ├── scheduler/
│   │   ├── nexus_scheduler/
│   │   │   ├── main.py             # APScheduler setup
│   │   │   ├── polling.py          # Per-connector polling jobs
│   │   │   └── webhook_renewal.py  # Auto-renew expiring webhooks
│   │   └── pyproject.toml
│   └── worker/
│       ├── nexus_worker/
│       │   ├── celery_app.py
│       │   ├── tasks/
│       │   │   ├── full_sync.py    # Bulk indexing jobs
│       │   │   ├── reindex.py      # Re-embed when model changes
│       │   │   └── cleanup.py      # Delete orphaned chunks
│       └── pyproject.toml
├── packages/
│   ├── core/
│   │   ├── nexus_core/
│   │   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── schemas/            # Pydantic request/response schemas
│   │   │   ├── config.py           # Settings (pydantic-settings)
│   │   │   ├── logging.py          # Structured logging setup
│   │   │   ├── tracing.py          # OpenTelemetry setup
│   │   │   └── crypto.py           # AES-256-GCM encryption helpers
│   │   └── pyproject.toml
│   ├── chunker/
│   │   ├── nexus_chunker/
│   │   │   ├── base.py
│   │   │   ├── fixed_window.py
│   │   │   ├── semantic.py
│   │   │   ├── parent_child.py
│   │   │   ├── heading_aware.py
│   │   │   └── metadata_first.py
│   │   └── pyproject.toml
│   └── retriever/
│       ├── nexus_retriever/
│       │   ├── query_router.py     # Classify query intent
│       │   ├── hyde.py             # HyDE query expansion
│       │   ├── multi_query.py      # Query variant generation
│       │   ├── dense.py            # Qdrant ANN search
│       │   ├── sparse.py           # Elasticsearch BM25
│       │   ├── rrf.py              # Reciprocal rank fusion
│       │   ├── permission.py       # ACL-aware chunk filtering
│       │   ├── reranker.py         # Cohere Rerank integration
│       │   ├── assembler.py        # Context assembly + formatting
│       │   ├── generator.py        # LLM call + streaming
│       │   └── citation.py         # Map citations to source URLs
│       └── pyproject.toml
├── infra/
│   ├── terraform/
│   │   ├── modules/
│   │   │   ├── eks/
│   │   │   ├── rds/
│   │   │   ├── elasticache/
│   │   │   └── msk/
│   │   └── envs/
│   │       ├── staging.tfvars
│   │       └── production.tfvars
│   ├── k8s/
│   │   ├── base/                   # Kustomize base manifests
│   │   ├── staging/                # Staging overlays
│   │   └── production/             # Production overlays
│   └── docker/
│       └── docker-compose.yml
├── evals/
│   ├── golden/                     # 100 Q&A pairs per connector
│   └── run_ragas.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── dashboard/                      # Next.js dashboard (optional)
├── .env.example
├── docker-compose.yml
├── Makefile
├── PLAN.md
└── README.md
```

---

## Contributing

### Branching

- `main` — production-ready, protected
- `develop` — integration branch
- `feature/xxx` — feature branches, PR into develop
- `fix/xxx` — bug fixes

### PR Requirements

- All CI checks passing (lint, type check, unit tests)
- At least one reviewer approval
- For connector changes: integration test added or updated

### Connector Contributions

Want to add a new connector? See [`docs/adding-connectors.md`](docs/adding-connectors.md) for the full guide. The connector interface is stable and adding a new source requires no changes to the core pipeline.

---

## License

Nexus core is MIT licensed. See [LICENSE](LICENSE).

Enterprise features (SSO, private deployment, audit logging, SLA) are available under a commercial license. See [usenexus.ai/pricing](https://usenexus.ai/pricing).

---

*Built by Wales — questions? [hi@usenexus.ai](mailto:hi@usenexus.ai)*
