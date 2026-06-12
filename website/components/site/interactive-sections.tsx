"use client";

import { useState } from "react";

import { quickstartSteps } from "@/components/site/data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const tabs = ["query", "stream", "sources", "sdk"] as const;

export function DeveloperTabs() {
  const [active, setActive] = useState<(typeof tabs)[number]>("query");

  return (
    <>
      <div className="tab-list reveal">
        {tabs.map((tab) => (
          <button
            className={`tab-btn ${active === tab ? "active" : ""}`}
            key={tab}
            onClick={() => setActive(tab)}
            type="button"
          >
            {tab === "sdk" ? "Python SDK" : tab === "stream" ? "Streaming" : tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className={`tab-panel ${active === "query" ? "active" : ""} reveal`}>
        <div className="api-block">
          <div className="api-bar">
            <span className="api-method">POST</span>
            <span className="api-path">/v1/query</span>
          </div>
          <div className="api-body">
            <div className="api-pane">
              <div className="api-pane-label">Request</div>
              <pre>
                <span className="sc"># Standard query with ACL filtering</span>
                {`
curl -X POST https://nexus.co/v1/query \\
  -H `}
                <span className="ss">"Authorization: Bearer nxs_..."</span>
                {` \\
  -H `}
                <span className="ss">"Content-Type: application/json"</span>
                {` \\
  -d '{
    `}
                <span className="sk">"query"</span>: <span className="ss">"What is our Q3 strategy?"</span>
                {`,
    `}
                <span className="sk">"connectors"</span>: [<span className="ss">"google_drive"</span>,{" "}
                <span className="ss">"notion"</span>],
                {`
    `}
                <span className="sk">"top_k"</span>: <span className="sn">5</span>,
                {`
    `}
                <span className="sk">"stream"</span>: <span className="sn">false</span>,
                {`
    `}
                <span className="sk">"user_email"</span>:{" "}
                <span className="ss">"alice@company.com"</span>
                {`
  }'`}
              </pre>
            </div>
            <div className="api-pane">
              <div className="api-pane-label">Response</div>
              <pre>
                {`{
  `}
                <span className="sk">"query_id"</span>: <span className="ss">"qry_01hz..."</span>,
                {`
  `}
                <span className="sk">"answer"</span>:{" "}
                <span className="ss">
                  "The Q3 strategy focuses on platform scalability and two new enterprise integrations..."
                </span>
                ,
                {`
  `}
                <span className="sk">"citations"</span>: [
                {`
    {
      `}
                <span className="sk">"connector"</span>: <span className="ss">"notion"</span>,
                {`
      `}
                <span className="sk">"title"</span>: <span className="ss">"Q3 Planning — Eng"</span>,
                {`
      `}
                <span className="sk">"url"</span>: <span className="ss">"https://notion.so/abc"</span>,
                {`
      `}
                <span className="sk">"score"</span>: <span className="sn">0.94</span>
                {`
    }
  ],
  `}
                <span className="sk">"latency_ms"</span>: <span className="sn">187</span>,
                {`
  `}
                <span className="sk">"cached"</span>: <span className="sn">false</span>
                {`
}`}
              </pre>
            </div>
          </div>
        </div>
      </div>

      <div className={`tab-panel ${active === "stream" ? "active" : ""} reveal`}>
        <div className="api-block">
          <div className="api-bar">
            <span className="api-method">POST</span>
            <span className="api-path">/v1/query (stream: true) — Server-Sent Events</span>
          </div>
          <div className="api-body">
            <div className="api-pane">
              <div className="api-pane-label">JavaScript</div>
              <pre>{`const res = await fetch('/v1/query', {
  method: 'POST',
  headers: { Authorization: 'Bearer nxs_...' },
  body: JSON.stringify({
    query: "What's our Q3 strategy?",
    stream: true,
    user_email: "alice@company.com"
  })
});

const reader = res.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  appendToken(decode(value));
}`}</pre>
            </div>
            <div className="api-pane">
              <div className="api-pane-label">SSE stream format</div>
              <pre>{`data: {"type":"token","text":"The "}
data: {"type":"token","text":"Q3 "}
data: {"type":"token","text":"strategy"}
...
data: {
  "type":"done",
  "citations": [...],
  "latency_ms": 140
}
data: [DONE]`}</pre>
            </div>
          </div>
        </div>
      </div>

      <div className={`tab-panel ${active === "sources" ? "active" : ""} reveal`}>
        <div className="api-block">
          <div className="api-bar">
            <span
              className="api-method"
              style={{ background: "var(--green-bg)", borderColor: "var(--green-border)", color: "var(--green)" }}
            >
              GET
            </span>
            <span className="api-path">/v1/sources</span>
          </div>
          <div className="api-body">
            <div className="api-pane">
              <div className="api-pane-label">List & manage</div>
              <pre>{`curl https://nexus.co/v1/sources \\
  -H "Authorization: Bearer nxs_..."

# Filter by connector
GET /v1/sources?connector=notion

# Trigger full sync
POST /v1/sources/src_id/sync

# Get sync status
GET /v1/sources/src_id/status`}</pre>
            </div>
            <div className="api-pane">
              <div className="api-pane-label">Response</div>
              <pre>{`{
  "sources": [{
    "id": "src_01hz...",
    "connector": "notion",
    "name": "Engineering workspace",
    "doc_count": 4882,
    "last_synced": "2025-06-10T14:22Z",
    "status": "healthy",
    "sync_mode": "webhook"
  }]
}`}</pre>
            </div>
          </div>
        </div>
      </div>

      <div className={`tab-panel ${active === "sdk" ? "active" : ""} reveal`}>
        <div className="api-block">
          <div className="api-bar">
            <span
              className="api-method"
              style={{ background: "#fdf4ff", borderColor: "#e9d5ff", color: "#9333ea" }}
            >
              PY
            </span>
            <span className="api-path">Python SDK — pip install nexus-sdk</span>
          </div>
          <div className="api-body">
            <div className="api-pane">
              <div className="api-pane-label">Install</div>
              <pre>{`$ pip install nexus-sdk

# Or with uv
$ uv add nexus-sdk`}</pre>
            </div>
            <div className="api-pane">
              <div className="api-pane-label">Usage</div>
              <pre>{`from nexus import NexusClient

client = NexusClient(
  base_url="https://nexus.company.com",
  api_key="nxs_prod_..."
)

result = client.query(
  query="What is our Q3 strategy?",
  connectors=["notion", "google_drive"],
  user_email="alice@company.com"
)

for c in result.citations:
  print(c.title, c.url, c.score)`}</pre>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export function Quickstart() {
  const [stepIndex, setStepIndex] = useState(0);
  const active = quickstartSteps[stepIndex];

  return (
    <section id="quickstart" className="section bg-white">
      <div className="container">
        <div className="mb-12 max-w-[560px]">
          <p className="section-eyebrow reveal">Developer quickstart</p>
          <h2 className="section-title reveal">Up and running in five minutes.</h2>
        </div>
        <div className="qs-grid">
          <div className="qs-steps reveal">
            {quickstartSteps.map((step, index) => (
              <button
                className={`qs-step ${index === stepIndex ? "active" : ""}`}
                key={step.title}
                onClick={() => setStepIndex(index)}
                type="button"
              >
                <div className="qs-step-num">{index + 1}</div>
                <div>
                  <div className="qs-step-title">{step.title}</div>
                  <div className="qs-step-desc">{step.desc}</div>
                </div>
              </button>
            ))}
          </div>
          <div className="terminal reveal" id="qs-terminal">
            <div className="terminal-bar">
              <div className="traffic-lights">
                <span className="tl tl-r" />
                <span className="tl tl-y" />
                <span className="tl tl-g" />
              </div>
              <span id="qs-term-title">{active.terminalTitle}</span>
            </div>
            <div className="terminal-body" id="qs-term-body">
              <pre dangerouslySetInnerHTML={{ __html: active.body }} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ContactForm() {
  const [submitted, setSubmitted] = useState(false);

  return (
    <div className="reveal">
      <div className="rounded-[var(--radius-xl)] border border-border bg-white p-7 shadow-panel">
        <form
          className="form-body"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(true);
          }}
        >
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="name">
                Name
              </label>
              <Input id="name" placeholder="Ada Lovelace" type="text" />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="email">
                Work email
              </label>
              <Input id="email" placeholder="ada@company.com" type="email" />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="company">
              Company
            </label>
            <Input id="company" placeholder="Acme Corp" type="text" />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="role">
              Role
            </label>
            <Select id="role" defaultValue="">
              <option value="">Select your role...</option>
              <option>CTO / VP Engineering</option>
              <option>AI / ML Engineer</option>
              <option>Platform Engineer</option>
              <option>Technical Founder</option>
              <option>Developer Relations</option>
              <option>Product Manager</option>
            </Select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="message">
              What are you building?
            </label>
            <Textarea
              id="message"
              placeholder="I'm building an internal knowledge agent that needs to query across Notion, Drive, and Slack..."
            />
          </div>
          <Button
            className={submitted ? "w-full justify-center !border-[var(--green)] !bg-[var(--green)] !py-[11px]" : "w-full justify-center !py-[11px]"}
            disabled={submitted}
            type="submit"
          >
            {submitted ? "Request received — we'll be in touch within one business day" : "Book a demo call ->"}
          </Button>
          <p className="text-center font-mono text-[11px] text-[var(--text-3)]">
            We respond within one business day. No spam, ever.
          </p>
        </form>
      </div>
    </div>
  );
}
