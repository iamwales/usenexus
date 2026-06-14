import { Code2, Github, Mail, MessageCircle, Shield } from "lucide-react";

import {
  agentFlow,
  blogPosts,
  connectorNames,
  connectors,
  deployments,
  features,
  footerLinks,
  navLinks,
  pricing,
  problems,
  sectionDots,
  securityItems,
  stats,
  useCases
} from "@/components/site/data";
import { ContactForm, DeveloperTabs, Quickstart } from "@/components/site/interactive-sections";
import { Icon, NexusMark } from "@/components/site/icons";
import { SiteMotion } from "@/components/site/site-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function TrafficLights() {
  return (
    <div className="traffic-lights">
      <span className="tl tl-r" />
      <span className="tl tl-y" />
      <span className="tl tl-g" />
    </div>
  );
}

function SectionDots() {
  return (
    <nav aria-hidden="true" className="side-dots">
      {sectionDots.map((section, index) => (
        <button className={`side-dot ${index === 0 ? "active" : ""}`} data-s={section} key={section} type="button" />
      ))}
    </nav>
  );
}

function Announcement() {
  return (
    <div className="announce">
      <Badge dot variant="green">
        v0.1 live
      </Badge>
      Nexus is open-source. MIT core license, 8 connectors, Docker in 5 minutes.
      <a href="#quickstart">Get started -&gt;</a>
    </div>
  );
}

function Header() {
  return (
    <nav className="main-nav" id="main-nav">
      <div className="nav-inner">
        <a className="nav-logo" href="#">
          <div className="nav-logo-mark">
            <NexusMark />
          </div>
          Nexus
        </a>
        <ul className="nav-links">
          {navLinks.map(([label, href]) => (
            <li key={label}>
              <a href={href}>{label}</a>
            </li>
          ))}
        </ul>
        <div className="nav-right">
          <Button asChild size="sm" variant="outline">
            <a href="https://github.com">
              <Github size={13} />
              GitHub
            </a>
          </Button>
          <Button asChild size="sm">
            <a href="#contact">Book demo</a>
          </Button>
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <div className="container" id="hero">
      <div className="hero-top">
        <div className="hero-announce reveal">
          <span className="hero-announce-pill">New</span>
          MCP-native connectors with full ACL support -&gt;
        </div>
        <h1 className="hero-h1 reveal">
          The knowledge layer
          <br />
          for company AI.
        </h1>
        <p className="hero-sub reveal">
          Connect Google Drive, Notion, Slack, ClickUp, GitHub, Linear, Calendar, and Confluence. Query
          everything through one permission-aware API with fresh, cited answers.
        </p>
        <div className="hero-ctas reveal">
          <Button asChild size="lg">
            <a href="#quickstart">
              <Code2 size={15} />
              Start with Docker
            </a>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href="https://github.com">
              <Github size={15} />
              Star on GitHub
            </a>
          </Button>
          <Button asChild size="lg" variant="ghost">
            <a href="#developers">Read the docs</a>
          </Button>
        </div>
        <div className="hero-meta reveal">
          <span className="hero-meta-item">
            <Icon name="FileText" />
            MIT license
          </span>
          <span className="hero-meta-item">
            <Icon name="Sparkles" />
            8 connectors
          </span>
          <span className="hero-meta-item">
            <Shield size={12} />
            ACL-aware
          </span>
          <span className="hero-meta-item">
            <Icon name="Clock" />
            &lt;200ms p95
          </span>
        </div>
      </div>

      <div className="query-card reveal">
        <div className="card-topbar">
          <TrafficLights />
          <span className="card-topbar-title">nexus — query console</span>
        </div>
        <div className="card-body">
          <div className="card-pane">
            <div className="pane-label">Request</div>
            <pre className="snippet">
              <span className="sk">POST</span> <span className="ss">/v1/query</span>
              {`
Authorization: Bearer nxs_...

{
  `}
              <span className="sk">"query"</span>:{" "}
              <span className="ss">"What is our Q3 ML platform hiring plan?"</span>,
              {`
  `}
              <span className="sk">"connectors"</span>: [
              {`
    `}
              <span className="ss">"notion"</span>, <span className="ss">"google_drive"</span>,{" "}
              <span className="ss">"slack"</span>, <span className="ss">"linear"</span>
              {`
  ],
  `}
              <span className="sk">"top_k"</span>: <span className="sn">5</span>,
              {`
  `}
              <span className="sk">"stream"</span>: <span className="sn">false</span>,
              {`
  `}
              <span className="sk">"user_email"</span>: <span className="ss">"alice@company.com"</span>
              {`
}`}
            </pre>
          </div>
          <div className="card-pane">
            <div className="pane-label">Response</div>
            <div className="res-block">
              <div className="res-source">notion · Engineering Planning Q3</div>
              <div className="res-text">
                The ML platform team plans to hire 3 senior engineers and 1 staff engineer in Q3,
                focused on distributed systems and LLM infrastructure...
              </div>
              <div className="res-footer">
                <span>score: 0.94</span>
                <span>notion://abc123</span>
              </div>
            </div>
            <div className="res-block">
              <div className="res-source">google_drive · Q3 OKRs Draft.docx</div>
              <div className="res-text">
                Platform headcount: +4 ICs, +1 EM. Budget approved for 2 contractors for the infra
                migration sprint...
              </div>
              <div className="res-footer">
                <span>score: 0.88</span>
                <span>drive://xyz456</span>
              </div>
            </div>
            <div className="res-footer mt-2.5 border-t border-border pt-2.5">
              <span className="latency">187ms</span>
              <span>5 chunks</span>
              <span>cache: miss</span>
              <span>acl: alice@</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LogosStrip() {
  return (
    <div className="logos-strip">
      <div className="logos-inner">
        <span className="logos-label">Works with</span>
        {connectorNames.map((name) => (
          <span className="logo-chip" key={name}>
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}

function StatsRow() {
  return (
    <div className="stats-row container max-w-full !px-0">
      {stats.map(([value, label]) => (
        <div className="stat-cell reveal" key={label}>
          <div className="stat-val">{value}</div>
          <div className="stat-lbl">{label}</div>
        </div>
      ))}
    </div>
  );
}

function Platform() {
  return (
    <section className="section" id="platform">
      <div className="container">
        <div className="two-col-header mb-[60px]">
          <div>
            <p className="section-eyebrow reveal">The problem</p>
            <h2 className="section-title reveal">
              Company knowledge is everywhere — and nowhere AI can reach it.
            </h2>
          </div>
          <div>
            <p className="section-sub reveal !max-w-none mt-10">
              Your team's decisions, docs, and context are scattered across a dozen SaaS tools. Building one-off
              connectors and brittle RAG pipelines is not infrastructure — it's technical debt that compounds every
              quarter.
            </p>
          </div>
        </div>

        <div className="three-col">
          {problems.map((problem) => (
            <div className="grid-cell reveal" key={problem.number}>
              <span className="prob-num">{problem.number}</span>
              <div className="prob-title">{problem.title}</div>
              <div className="prob-body">{problem.body}</div>
            </div>
          ))}
        </div>

        <div className="mt-20">
          <div className="two-col-header mb-12">
            <div>
              <p className="section-eyebrow reveal">The solution</p>
              <h2 className="section-title reveal">One API. Everything your company knows.</h2>
            </div>
            <div>
              <p className="section-sub reveal !max-w-none mt-10">
                Nexus is the company knowledge layer for AI. It connects to every tool your team uses, indexes their
                contents continuously, and serves fresh, cited, permission-filtered answers through a single query
                endpoint.
              </p>
              <div className="reveal mt-5">
                <Button asChild className="mr-2" variant="outline">
                  <a href="#developers">API reference</a>
                </Button>
                <Button asChild variant="ghost">
                  <a href="#quickstart">Quickstart</a>
                </Button>
              </div>
            </div>
          </div>

          <div className="three-col [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
            {features.map((feature) => (
              <div className="grid-cell reveal" key={feature.title}>
                <div className="feat-icon-wrap">
                  <Icon name={feature.icon} />
                </div>
                <div className="feat-title">{feature.title}</div>
                <div className="feat-body">{feature.body}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Architecture() {
  return (
    <div className="arch-band">
      <div className="container">
        <p className="section-eyebrow reveal mb-5">System architecture</p>
        <div className="arch-strip reveal">
          <div className="arch-flow">
            <div className="arch-node-group">
              <div className="arch-node">Google Drive</div>
              <div className="arch-node">Notion</div>
              <div className="arch-node">Slack</div>
              <div className="arch-node text-[11px] text-[var(--text-3)]">+ 5 more</div>
            </div>
            <div className="arch-arrow !w-9" />
            <div className="arch-node hl">MCP connectors</div>
            <div className="arch-arrow" />
            <div className="arch-node">Kafka / MSK</div>
            <div className="arch-arrow" />
            <div className="arch-node-group">
              <div className="arch-node">Chunker</div>
              <div className="arch-node">Embedder</div>
            </div>
            <div className="arch-arrow" />
            <div className="arch-node-group">
              <div className="arch-node hl-blue">Qdrant</div>
              <div className="arch-node hl-blue">Elasticsearch</div>
            </div>
            <div className="arch-arrow" />
            <div className="arch-node">Cohere reranker</div>
            <div className="arch-arrow" />
            <div className="arch-node hl">Query API</div>
            <div className="arch-arrow" />
            <div className="arch-node border-[var(--green-border)] bg-[var(--green-bg)] text-[var(--green)]">
              Cited answer
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Connectors() {
  return (
    <section className="section" id="connectors">
      <div className="container">
        <div className="two-col-header mb-12">
          <div>
            <p className="section-eyebrow reveal">Connectors</p>
            <h2 className="section-title reveal">Eight connectors. More on the way.</h2>
            <p className="section-sub reveal">
              Each connector implements{" "}
              <code className="font-mono text-xs text-[var(--blue)]">BaseConnector</code>: full sync, webhook
              subscription, incremental sync, and polling fallback. Contribute your own in one Python file.
            </p>
            <div className="reveal mt-5">
              <Button asChild size="sm" variant="outline">
                <a href="#oss">Contribute a connector</a>
              </Button>
            </div>
          </div>
          <div className="reveal">
            <div className="terminal">
              <div className="terminal-bar">
                <TrafficLights />
                <span>nexus connectors status</span>
              </div>
              <div className="terminal-body">
                <pre>{`✓ google_drive    synced 3m ago   12,441 docs
✓ notion          synced 1m ago    4,882 pages
✓ slack           live (events)   89,214 msgs
✓ github          synced 8m ago    2,317 files
✓ linear          synced 2m ago    7,620 issues
✓ confluence      synced 4m ago    3,109 pages
✓ clickup         synced 6m ago    5,540 tasks
✓ google_calendar live             891 events`}</pre>
              </div>
            </div>
          </div>
        </div>

        <div className="conn-grid">
          {connectors.map((connector) => (
            <div className="conn-card reveal" key={connector.name}>
              <div className="conn-logo">{connector.logo}</div>
              <div>
                <div className="conn-name">{connector.name}</div>
                <div className="conn-desc">{connector.desc}</div>
                <div className="conn-tags">
                  {connector.tags.map((tag) => (
                    <span className="ctag" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="custom-connector reveal">
          <div>
            <p className="section-eyebrow mb-2.5">Custom connectors</p>
            <div className="mb-2 text-[15px] font-semibold text-[var(--text)]">Extend with your own sources</div>
            <p className="text-[13px] leading-[1.7] text-[var(--text-2)]">
              Implement <code className="font-mono text-[11.5px] text-[var(--blue)]">BaseConnector</code> in Python.
              Your connector inherits OAuth scaffolding, chunk storage, and webhook routing automatically.
            </p>
            <div className="mt-4">
              <Button asChild size="sm" variant="outline">
                <a href="#oss">View contribution guide</a>
              </Button>
            </div>
          </div>
          <div className="code-box">
            <pre>{`from nexus.connectors import BaseConnector

class MyConnector(BaseConnector):
  name = "my_connector"

  async def full_sync(self):
    # Yield Document objects
    async for doc in self.fetch_all():
      yield doc

  async def handle_webhook(self, payload):
    yield self.parse(payload)`}</pre>
          </div>
        </div>
      </div>
    </section>
  );
}

function Agents() {
  return (
    <section className="section bg-white" id="agents">
      <div className="container">
        <div className="mb-12 max-w-[640px]">
          <p className="section-eyebrow reveal">Agent infrastructure</p>
          <h2 className="section-title reveal">Nexus is not a chatbot. It's memory for your agents.</h2>
          <p className="section-sub reveal">
            AI agents need governed, fresh, citable context — not a vector store bolted on after the fact. Nexus is the
            single tool your agents call to know anything your company knows, within the permissions of the requesting
            user.
          </p>
        </div>

        <div className="two-col">
          <div>
            <p className="reveal mb-3.5 text-[13px] font-semibold text-[var(--text)]">Agent use cases</p>
            <div className="use-case-list">
              {useCases.map((useCase) => (
                <div className="uc-item reveal" key={useCase.title}>
                  <Icon className="uc-icon" name={useCase.icon} />
                  <div>
                    <div className="uc-title">{useCase.title}</div>
                    <div className="uc-desc">{useCase.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="reveal">
            <p className="mb-3.5 text-[13px] font-semibold text-[var(--text)]">Integration flow</p>
            <div className="flow-card">
              {agentFlow.map(([title, body, code], index) => (
                <div className="flow-step" key={title}>
                  <div className="flow-num">{index + 1}</div>
                  <div>
                    <div className="flow-title">{title}</div>
                    <div className="flow-body">{body}</div>
                    {code ? <span className="flow-code">{code}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Developers() {
  return (
    <section className="section" id="developers">
      <div className="container">
        <div className="mb-12 max-w-[600px]">
          <p className="section-eyebrow reveal">Developers</p>
          <h2 className="section-title reveal">An API developers actually want to use.</h2>
          <p className="section-sub reveal">
            One authenticated endpoint. Consistent JSON. Streaming SSE. Works with LangChain, LlamaIndex, AutoGen, and
            raw API calls.
          </p>
        </div>
        <DeveloperTabs />
      </div>
    </section>
  );
}

function Deployment() {
  return (
    <section className="section" id="deployment">
      <div className="container">
        <div className="mb-12 max-w-[580px]">
          <p className="section-eyebrow reveal">Deployment</p>
          <h2 className="section-title reveal">Deploy anywhere. Own your infrastructure.</h2>
          <p className="section-sub reveal">
            Nexus is designed for private deployment. Your data stays inside your perimeter. Run locally, on-prem, or
            in your own AWS account.
          </p>
        </div>
        <div className="deploy-grid">
          {deployments.map((deployment) => (
            <div className={`deploy-card reveal ${deployment.featured ? "featured" : ""}`} key={deployment.name}>
              <span className="deploy-badge">{deployment.badge}</span>
              <div className="deploy-name">{deployment.name}</div>
              <div className="deploy-desc">{deployment.desc}</div>
              <ul className="check-list">
                {deployment.checks.map((check) => (
                  <li key={check}>{check}</li>
                ))}
              </ul>
              {deployment.chips ? (
                <div className="infra-chips">
                  {deployment.chips.map((chip) => (
                    <span className="infra-chip" key={chip}>
                      {chip}
                    </span>
                  ))}
                </div>
              ) : null}
              {deployment.featured ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button asChild size="sm">
                    <a href="#contact">Talk to the team</a>
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <a href="#developers">Deployment docs</a>
                  </Button>
                </div>
              ) : deployment.cta ? (
                <div className="mt-5">
                  <Button asChild size="sm" variant="outline">
                    <a href={deployment.cta[1]}>{deployment.cta[0]}</a>
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Security() {
  return (
    <section className="section bg-white" id="security">
      <div className="container">
        <div className="mb-12 max-w-[560px]">
          <p className="section-eyebrow reveal">Security</p>
          <h2 className="section-title reveal">Security is not a feature flag.</h2>
          <p className="section-sub reveal">
            Permission-aware retrieval, encrypted credentials, per-tenant isolation, and audit logging are foundational
            — not enterprise add-ons.
          </p>
        </div>
        <div className="sec-grid">
          {securityItems.map((item) => (
            <div className="sec-cell reveal" key={item.title}>
              <Icon className="sec-icon" name={item.icon} />
              <div className="sec-title">{item.title}</div>
              <div className="sec-body">{item.body}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function OpenSource() {
  const enterpriseItems = [
    "Managed cloud (your VPC or ours)",
    "Full audit logging + SIEM export",
    "SSO / SAML / SCIM provisioning",
    "99.9% uptime SLA",
    "Dedicated onboarding + support",
    "Custom connector development"
  ];

  return (
    <section className="section" id="oss">
      <div className="container">
        <div className="mb-12 max-w-[560px]">
          <p className="section-eyebrow reveal">Open source</p>
          <h2 className="section-title reveal">Built in public. Open-core forever.</h2>
          <p className="section-sub reveal">
            Nexus is MIT-licensed at the core. The connector framework, ingestion pipeline, retrieval engine, and query
            API are all open source. Enterprise features are available commercially.
          </p>
        </div>
        <div className="oss-grid">
          <div className="reveal bg-white p-7">
            <div className="mb-1 text-sm font-bold text-[var(--text)]">Open Core</div>
            <div className="mb-1 text-[28px] font-bold tracking-[-0.04em] text-[var(--text)]">
              $0 <span className="text-[13px] font-normal text-[var(--text-2)]">/ forever</span>
            </div>
            <div className="mb-[18px] text-[12.5px] text-[var(--text-2)]">
              Self-host on your own infra. MIT license, no seat limits.
            </div>
            <ul className="check-list mb-[22px]">
              {[
                "All 8 native connectors",
                "BaseConnector for custom sources",
                "Hybrid retrieval + Cohere reranking",
                "ACL-aware filtering",
                "Citations in all responses",
                "Docker + Kubernetes support",
                "Community support on GitHub"
              ].map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <Button asChild className="w-full justify-center" variant="outline">
              <a href="https://github.com">Star on GitHub</a>
            </Button>
          </div>
          <div className="reveal bg-white p-7">
            <div className="mb-1 text-sm font-bold text-[var(--text)]">Self-hosted Pro</div>
            <div className="mb-1 text-[28px] font-bold tracking-[-0.04em] text-[var(--text)]">
              $0 <span className="text-[13px] font-normal text-[var(--text-2)]">under 5M docs</span>
            </div>
            <div className="mb-[18px] text-[12.5px] text-[var(--text-2)]">
              Everything in Open Core plus production tooling.
            </div>
            <ul className="check-list mb-[22px]">
              {[
                "Everything in Open Core",
                "Audit logging (local export)",
                "Priority community support",
                "Production Helm charts",
                "Terraform modules"
              ].map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <Button asChild className="w-full justify-center" variant="outline">
              <a href="#contact">Contact for large scale</a>
            </Button>
          </div>
          <div className="reveal bg-[var(--text)] p-7">
            <div className="mb-1 text-sm font-bold text-white">Enterprise</div>
            <div className="mb-1 text-[28px] font-bold tracking-[-0.04em] text-white">Custom</div>
            <div className="mb-[18px] text-[12.5px] text-white/55">
              Volume pricing, dedicated support, SLAs.
            </div>
            <ul className="mb-[22px] flex list-none flex-col gap-2">
              {enterpriseItems.map((item) => (
                <li className="flex gap-2 text-[12.5px] text-white/70" key={item}>
                  <span className="shrink-0 text-[#4ade80]">✓</span>
                  {item}
                </li>
              ))}
            </ul>
            <Button asChild className="w-full justify-center" variant="inverted">
              <a href="#contact">Book enterprise demo</a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section className="section bg-white" id="pricing">
      <div className="container">
        <div className="mb-12 max-w-[500px]">
          <p className="section-eyebrow reveal">Pricing</p>
          <h2 className="section-title reveal">Simple pricing. No surprises.</h2>
        </div>
        <div className="pricing-grid">
          {pricing.map((plan) => (
            <div className={`price-cell reveal ${plan.featured ? "featured" : ""}`} key={plan.name}>
              <div className="flex items-start justify-between">
                <div className="price-name">{plan.name}</div>
                {plan.featured ? (
                  <span className="rounded-full bg-white/15 px-2 py-0.5 font-mono text-[10.5px] text-white/80">
                    Beta
                  </span>
                ) : null}
              </div>
              <div className={`price-val ${plan.name === "Enterprise" ? "!text-[26px]" : ""}`}>
                {plan.price} {plan.suffix ? <sub>{plan.suffix}</sub> : null}
              </div>
              <div className="price-desc">{plan.desc}</div>
              <div className="price-div" />
              <ul className="price-feats">
                {plan.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
                {plan.off.map((feature) => (
                  <li className="off" key={feature}>
                    {feature}
                  </li>
                ))}
              </ul>
              <Button
                asChild
                className="w-full justify-center"
                variant={plan.featured ? "inverted" : plan.name === "Enterprise" ? "default" : "outline"}
              >
                <a href={plan.href}>{plan.cta}</a>
              </Button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Blog() {
  return (
    <section className="section" id="blog">
      <div className="container">
        <div className="mb-9 flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="section-eyebrow reveal">Blog & resources</p>
            <h2 className="section-title reveal !mb-0">From the Nexus team.</h2>
          </div>
          <Button asChild className="reveal" size="sm" variant="outline">
            <a href="#">View all posts</a>
          </Button>
        </div>
        <div className="blog-grid">
          {blogPosts.map(([tag, title, meta]) => (
            <a className="blog-card reveal" href="#" key={title}>
              <div className="blog-tag">{tag}</div>
              <div className="blog-title">{title}</div>
              <div className="blog-meta">{meta}</div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <div id="final-cta">
      <div className="container">
        <h2 className="cta-h reveal">
          Build AI on top of the knowledge
          <br />
          your company already has.
        </h2>
        <p className="cta-sub reveal">
          Stop building one-off connectors and brittle pipelines. Give every AI system in your company a single,
          permission-aware, always-fresh knowledge API.
        </p>
        <div className="cta-btns reveal">
          <Button asChild className="border-white bg-white text-[var(--text)]" size="lg">
            <a href="#quickstart">
              <Code2 size={15} />
              Start with Docker
            </a>
          </Button>
          <Button asChild className="border-white/20 bg-transparent text-white/75" size="lg" variant="outline">
            <a href="https://github.com">Star on GitHub</a>
          </Button>
          <Button asChild className="border-white/20 bg-transparent text-white/75" size="lg" variant="outline">
            <a href="#contact">Book a demo</a>
          </Button>
        </div>
        <p className="cta-note reveal">MIT open-core · No credit card for self-hosting · Enterprise support available</p>
      </div>
    </div>
  );
}

function Contact() {
  return (
    <section className="section" id="contact">
      <div className="container">
        <div className="form-grid">
          <div>
            <p className="section-eyebrow reveal">Contact</p>
            <h2 className="section-title reveal">Book a demo or talk to the team.</h2>
            <p className="reveal mb-7 text-sm leading-[1.8] text-[var(--text-2)]">
              We work directly with platform teams and AI engineering leads at companies building internal AI systems.
              Tell us what you're building.
            </p>
            <div className="reveal flex flex-col gap-3">
              {[
                [Mail, "hello@nexus.sh", "mailto:hello@nexus.sh"],
                [MessageCircle, "discord.gg/nexus", "https://discord.gg/nexus"],
                [Github, "github.com/nexus-ai/nexus", "https://github.com/nexus-ai/nexus"]
              ].map(([ContactIcon, label, href]) => (
                <div className="flex items-center gap-2.5 text-[13.5px] text-[var(--text-2)]" key={String(label)}>
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] border border-border bg-white">
                    <ContactIcon aria-hidden="true" size={16} />
                  </span>
                  <a className="font-mono text-[13px] text-[var(--blue)] no-underline" href={String(href)}>
                    {String(label)}
                  </a>
                </div>
              ))}
            </div>
          </div>
          <ContactForm />
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer>
      <div className="footer-inner">
        <div className="footer-grid">
          <div>
            <div className="footer-brand">Nexus</div>
            <div className="footer-tagline">The knowledge layer for company AI. Connect everything. Know everything.</div>
            <div className="footer-socials">
              <Button asChild size="sm" variant="outline">
                <a href="https://github.com">GitHub</a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href="https://discord.gg">Discord</a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href="https://x.com">X</a>
              </Button>
            </div>
          </div>
          {Object.entries(footerLinks).map(([group, links]) => (
            <div key={group}>
              <div className="footer-col-title">{group}</div>
              <ul className="footer-links">
                {links.map(([label, href]) => (
                  <li key={label}>
                    <a href={href}>{label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="footer-bottom">
          <div className="footer-copy">© 2025 Nexus. MIT License for open-core features.</div>
          <div className="footer-chips">
            {["v0.1.0", "MIT core", "8 connectors", "Self-hostable"].map((chip) => (
              <span className="footer-chip" key={chip}>
                {chip}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}

export function MarketingPage() {
  return (
    <>
      <SiteMotion />
      <Announcement />
      <Header />
      <SectionDots />
      <Hero />
      <LogosStrip />
      <StatsRow />
      <Platform />
      <Architecture />
      <Connectors />
      <Agents />
      <Developers />
      <Quickstart />
      <Deployment />
      <Security />
      <OpenSource />
      <Pricing />
      <Blog />
      <FinalCta />
      <Contact />
      <Footer />
    </>
  );
}
