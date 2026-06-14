export const navLinks = [
  ["Platform", "#platform"],
  ["Connectors", "#connectors"],
  ["Agents", "#agents"],
  ["Developers", "#developers"],
  ["Deploy", "#deployment"],
  ["Security", "#security"],
  ["Pricing", "#pricing"],
  ["Blog", "#blog"]
] as const;

export const sectionDots = [
  "hero",
  "platform",
  "connectors",
  "agents",
  "developers",
  "deployment",
  "security",
  "oss",
  "pricing",
  "contact"
];

export const connectorNames = [
  "Google Drive",
  "Notion",
  "Slack",
  "GitHub",
  "Linear",
  "ClickUp",
  "Confluence",
  "Calendar"
];

export const stats = [
  ["8", "Native connectors"],
  ["<200ms", "p95 query latency"],
  ["5 min", "Local setup"],
  ["MIT", "Core license"],
  ["100%", "ACL-respecting"]
] as const;

export const problems = [
  {
    number: "01",
    title: "Knowledge is fragmented",
    body: "Decisions in Notion, code in GitHub, threads in Slack, tasks in Linear. No AI system can reason across all of it without a unified layer beneath."
  },
  {
    number: "02",
    title: "Agents hallucinate without context",
    body: "LLMs have no access to your private company knowledge. Without fresh, permission-aware context, agents fabricate answers — and users learn not to trust them."
  },
  {
    number: "03",
    title: "RAG pipelines are brittle",
    body: "Stale embeddings. No permission filtering. No citations. Every team reinvents the same connector logic and inherits the same failure modes."
  }
];

export const features = [
  {
    icon: "Clock",
    title: "Continuous sync",
    body: "Webhooks for real-time updates. Polling fallback. Incremental ingestion keeps your index hours-fresh, not weeks-stale."
  },
  {
    icon: "Search",
    title: "Hybrid retrieval",
    body: "Qdrant vector search + Elasticsearch BM25, fused with RRF. Cohere reranker for final relevance. Best of both worlds."
  },
  {
    icon: "Shield",
    title: "ACL-aware filtering",
    body: "Source permissions stored at index time. Every query is filtered per user_email — users see only what they can access."
  },
  {
    icon: "FileText",
    title: "Citations included",
    body: "Every answer includes source title, URL, section, and confidence score. Agents can surface verifiable links directly to users."
  },
  {
    icon: "Code2",
    title: "OAuth connectors",
    body: "Secure OAuth 2.0 flows for every supported source. No credentials stored. Tokens encrypted at rest with AES-256 and KMS."
  },
  {
    icon: "Globe2",
    title: "One query API",
    body: "POST /v1/query. Filter by connector, user, date range. Streaming SSE. JSON with answer, citations, latency, and cache metadata."
  }
];

export const connectors = [
  {
    logo: "G",
    name: "Google Drive",
    desc: "Docs, Sheets, Slides, PDFs. Real-time webhook sync.",
    tags: ["webhooks", "files", "oauth"]
  },
  {
    logo: "N",
    name: "Notion",
    desc: "Pages, databases, rows. Webhooks + polling fallback.",
    tags: ["webhooks", "databases", "oauth"]
  },
  {
    logo: "S",
    name: "Slack",
    desc: "Messages, threads, files. Slack Events API.",
    tags: ["events api", "threads", "oauth"]
  },
  {
    logo: "GH",
    name: "GitHub",
    desc: "Markdown docs, issues, PRs. Webhook-driven.",
    tags: ["webhooks", "issues", "markdown"]
  },
  {
    logo: "L",
    name: "Linear",
    desc: "Issues, projects, comments, roadmaps.",
    tags: ["webhooks", "issues", "projects"]
  },
  {
    logo: "CU",
    name: "ClickUp",
    desc: "Tasks, docs, comments, spaces.",
    tags: ["webhooks", "tasks", "docs"]
  },
  {
    logo: "CF",
    name: "Confluence",
    desc: "Pages, blog posts, spaces. Cloud + Data Center.",
    tags: ["webhooks", "pages", "cloud"]
  },
  {
    logo: "GC",
    name: "Google Calendar",
    desc: "Events, attendees, meeting notes.",
    tags: ["webhooks", "events", "oauth"]
  }
];

export const useCases = [
  {
    icon: "Handshake",
    title: "Internal support agent",
    desc: "Answers employee questions with citations from Confluence, Notion, and Slack."
  },
  {
    icon: "Cog",
    title: "Engineering knowledge agent",
    desc: "Surfaces ADRs, PRs, and Linear issues for engineers working on a feature."
  },
  {
    icon: "TrendingUp",
    title: "Sales research agent",
    desc: "Pulls account history from Drive, CRM notes, and Slack for pre-call briefings."
  },
  {
    icon: "ClipboardList",
    title: "Product ops assistant",
    desc: "Tracks decisions, blockers, and status across Linear and ClickUp."
  },
  {
    icon: "BarChart3",
    title: "Executive briefing bot",
    desc: "Summarises the week from calendar, Slack, and key docs — with citations."
  },
  {
    icon: "RefreshCw",
    title: "Workflow automation agent",
    desc: "Triggers actions based on retrieved knowledge — route tickets, draft replies."
  }
];

export const agentFlow = [
  ["User asks a question", "Natural-language question enters your agent or copilot interface."],
  [
    "Agent calls Nexus",
    "Agent issues a POST with the question and the user's email for ACL filtering.",
    'POST /v1/query  ->  user_email: "alice@co.com"'
  ],
  [
    "Permission-aware context returned",
    "Hybrid search + ACL filter + reranker. Only chunks Alice can access are returned."
  ],
  [
    "Agent answers with citations",
    "LLM uses grounded context. Each source chunk includes URL and title for citation."
  ],
  [
    "User verifies sources",
    "Cited links — Notion pages, Drive docs, Slack threads. Trust is built through transparency."
  ]
] as const;

export const quickstartSteps = [
  {
    title: "Clone the repo",
    desc: "Get the source and example config",
    terminalTitle: "bash — clone",
    body: `<span class="t-m"># Clone the repo</span>
<span class="t-p">$</span> <span class="t-c">git clone https://github.com/nexus-ai/nexus</span>
<span class="t-p">$</span> <span class="t-c">cd nexus</span>`
  },
  {
    title: "Configure environment",
    desc: "Copy .env.example, add API and OAuth keys",
    terminalTitle: "bash — configure",
    body: `<span class="t-m"># Configure environment</span>
<span class="t-p">$</span> <span class="t-c">cp .env.example .env</span>
<span class="t-p">$</span> <span class="t-c">vim .env</span>
<span class="t-o"># OPENAI_API_KEY=sk-...
# COHERE_API_KEY=...
# NOTION_CLIENT_ID=...
# GOOGLE_CLIENT_ID=...</span>`
  },
  {
    title: "Start all services",
    desc: "Docker Compose brings up Postgres, Redis, Qdrant, Elasticsearch, Kafka, Nexus API",
    terminalTitle: "bash — docker compose",
    body: `<span class="t-m"># Start all services</span>
<span class="t-p">$</span> <span class="t-c">docker compose up -d</span>
<span class="t-s">✓ postgres started</span>
<span class="t-s">✓ redis started</span>
<span class="t-s">✓ qdrant started</span>
<span class="t-s">✓ elasticsearch started</span>
<span class="t-s">✓ kafka started</span>
<span class="t-s">✓ nexus-api started on :8000</span>`
  },
  {
    title: "Run migrations",
    desc: "Alembic initialises schema for your tenant",
    terminalTitle: "bash — migrations",
    body: `<span class="t-m"># Run database migrations</span>
<span class="t-p">$</span> <span class="t-c">docker exec nexus-api alembic upgrade head</span>
<span class="t-s">✓ migrations complete</span>`
  },
  {
    title: "Create org + connect source",
    desc: "Bootstrap tenant, OAuth into a connector, trigger full sync",
    terminalTitle: "bash — org setup",
    body: `<span class="t-m"># Create org and connect Notion</span>
<span class="t-p">$</span> <span class="t-c">nexus org create --name "Acme Corp"</span>
<span class="t-s">✓ org_id: org_01hz...
✓ api_key: nxs_prod_...</span>

<span class="t-p">$</span> <span class="t-c">nexus connect notion --org org_01hz...</span>
<span class="t-o"># Opens OAuth flow in browser</span>
<span class="t-s">✓ Notion connected. Syncing 4,882 pages...</span>`
  },
  {
    title: "Make your first query",
    desc: "POST to /v1/query and get a cited answer in under 200ms",
    terminalTitle: "bash — first query",
    body: `<span class="t-m"># Make your first query!</span>
<span class="t-p">$</span> <span class="t-c">nexus query "What is our hiring plan?"</span>
<span class="t-s">-> "The Q3 hiring plan includes..."</span>
<span class="t-o">  [notion: Q3 Engineering Planning, 0.94]
  [latency: 187ms]</span>`
  }
];

export const deployments = [
  {
    badge: "Local / Staging",
    name: "Docker Compose",
    desc: "All services in one compose file. Perfect for local development, demos, and staging. One command to start everything.",
    checks: [
      "Postgres, Redis, Qdrant, Elasticsearch, Kafka — all included",
      "Pre-built .env.example with every required variable",
      "Hot reload for connector development",
      "Volume mounts for persistent storage"
    ],
    cta: ["View quickstart ↑", "#quickstart"]
  },
  {
    badge: "Production",
    name: "AWS / EKS",
    featured: true,
    desc: "Production-grade AWS deployment with Terraform, EKS, managed services, CI/CD, and ArgoCD GitOps. HA and automatic rollback built in.",
    checks: [
      "Terraform modules: VPC, EKS, RDS Postgres, ElastiCache Redis",
      "AWS MSK or Redpanda for ingestion queue",
      "Qdrant on EKS with persistent EBS volumes",
      "AWS OpenSearch Service for BM25",
      "GitHub Actions pipeline: lint -> test -> build -> deploy",
      "ArgoCD for GitOps Kubernetes reconciliation",
      "HPA on query and ingestion services",
      "CloudWatch alarms + automated RDS snapshots",
      "One-command rollback with ArgoCD history"
    ],
    chips: ["Terraform", "EKS", "RDS", "ElastiCache", "MSK", "OpenSearch", "S3", "ArgoCD", "Helm"]
  },
  {
    badge: "Self-managed",
    name: "Bare metal / VMs",
    desc: "Full control, no cloud dependency. Run each service on dedicated hardware with maximum data isolation.",
    checks: [
      "Systemd service files for each component",
      "Nginx reverse proxy config included",
      "Supports on-prem Postgres, Redis, Elasticsearch",
      "Air-gapped deployment guide available"
    ],
    cta: ["Contact for on-prem", "#contact"]
  }
];

export const securityItems = [
  {
    icon: "Lock",
    title: "Permission-aware retrieval",
    body: "Every chunk stores source ACL metadata at index time. Results are filtered to chunks the requesting user_email can access in the source system. No over-sharing."
  },
  {
    icon: "ShieldCheck",
    title: "Encrypted OAuth tokens",
    body: "OAuth tokens encrypted with AES-256 at rest using a per-tenant key. Keys stored in AWS KMS or HashiCorp Vault — never in the database directly."
  },
  {
    icon: "KeyRound",
    title: "API keys and JWT auth",
    body: "API keys use a nxs_ prefix with BLAKE3 hashing. JWT tokens (RS256) for user-scoped sessions. Rotation and revocation supported out of the box."
  },
  {
    icon: "Building2",
    title: "Per-tenant isolation",
    body: "Each organisation has isolated Postgres schemas, separate Qdrant collections, and namespaced Elasticsearch indices. Cross-tenant data leakage is architecturally prevented."
  },
  {
    icon: "Zap",
    title: "Rate limiting",
    body: "Per-tenant rate limits via Redis sliding window counters. Burst allowances, custom limits per API key, and 429 responses with Retry-After headers."
  },
  {
    icon: "ClipboardCheck",
    title: "Audit logging (Enterprise)",
    body: "Structured audit trail of every query, connector event, and admin action. Exportable to S3, Splunk, or any SIEM via webhook for SOC 2 compliance."
  },
  {
    icon: "Home",
    title: "Private deployment",
    body: "Deploy entirely within your own VPC. No data leaves your perimeter. Nexus calls your LLM API directly — documents are never sent to Nexus cloud infra."
  },
  {
    icon: "ScanSearch",
    title: "Network isolation",
    body: "Connectors run in a sandboxed worker pool with egress controls. Qdrant, Postgres, Redis, and Kafka are on private subnets with no public exposure."
  }
];

export const pricing = [
  {
    name: "Open Source",
    price: "$0",
    suffix: "/ month",
    desc: "Self-host on your own infra. MIT license. No seat limits.",
    cta: "Get started free",
    href: "https://github.com",
    features: [
      "All 8 connectors",
      "Unlimited documents",
      "ACL-aware retrieval",
      "Citations in responses",
      "Docker + Kubernetes",
      "Community support"
    ],
    off: ["Managed cloud hosting", "Audit logging", "SSO / SAML"]
  },
  {
    name: "Cloud",
    price: "$499",
    suffix: "/ month",
    desc: "Managed Nexus in your AWS VPC. We run it; you own the data.",
    cta: "Start trial",
    href: "#contact",
    featured: true,
    features: [
      "Everything in Open Source",
      "Managed in your AWS VPC",
      "Up to 10M documents",
      "Automated backups",
      "Monitoring + alerting",
      "Email support"
    ],
    off: ["Audit logging", "SSO / SAML"]
  },
  {
    name: "Enterprise",
    price: "Custom",
    desc: "Volume pricing, dedicated support, compliance, and SLAs.",
    cta: "Contact sales",
    href: "#contact",
    features: [
      "Everything in Cloud",
      "Unlimited documents",
      "Full audit logging",
      "SSO / SAML / SCIM",
      "99.9% uptime SLA",
      "Dedicated Slack channel",
      "Security review",
      "Custom connector dev"
    ],
    off: []
  }
];

export const blogPosts = [
  ["Engineering", "Building a production RAG pipeline: what we learned from 50 deployments", "June 5, 2025 · 12 min read"],
  [
    "Architecture",
    "Why hybrid retrieval (vector + BM25) outperforms pure embedding search for enterprise knowledge",
    "May 28, 2025 · 9 min read"
  ],
  ["Open Source", "Nexus v0.1 — what's in the release, what's next, and how to contribute", "May 20, 2025 · 6 min read"],
  [
    "Agents",
    "The knowledge layer pattern: how well-designed agent infrastructure changes what's possible",
    "May 12, 2025 · 10 min read"
  ],
  [
    "Security",
    "ACL-aware retrieval: how Nexus ensures agents never expose content to unauthorized users",
    "May 4, 2025 · 8 min read"
  ],
  [
    "Connectors",
    "Freshness matters: continuous sync architecture for enterprise SaaS connectors",
    "April 25, 2025 · 7 min read"
  ]
] as const;

export const footerLinks = {
  Product: [
    ["Platform", "#platform"],
    ["Connectors", "#connectors"],
    ["Agents", "#agents"],
    ["API docs", "#developers"],
    ["Quickstart", "#quickstart"]
  ],
  Deploy: [
    ["Docker Compose", "#deployment"],
    ["AWS / EKS", "#deployment"],
    ["Self-managed", "#deployment"],
    ["Open source", "#oss"],
    ["Pricing", "#pricing"]
  ],
  Company: [
    ["Blog", "#blog"],
    ["Contact", "#contact"],
    ["Book demo", "#contact"],
    ["Security", "#security"],
    ["Privacy", "#"]
  ],
  Community: [
    ["GitHub Discussions", "#"],
    ["Discord", "#"],
    ["Changelog", "#"],
    ["Contributing", "#"],
    ["Roadmap", "#"]
  ]
} as const;
