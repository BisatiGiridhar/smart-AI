import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AgentScene } from "../components/Scene3D";
import { Badge, ErrorNote, Loading, PageHeader, Panel, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import type { AgentsRes } from "./Workflow";

const LAYERS = [
  ["Frontend", "React, TypeScript, Vite, Tailwind CSS, React Three Fiber, TanStack Query, Recharts."],
  ["API", "FastAPI with server-side role checks, workspace isolation, rate limiting, structured JSON logs and an audit log."],
  ["Orchestration", "LangGraph state graph over typed node functions; an explicit sequential executor runs the same nodes when LangGraph is absent."],
  ["Retrieval", "Own BM25 implementation, Sentence Transformers embeddings in ChromaDB, Reciprocal Rank Fusion, cross-encoder reranking."],
  ["Storage", "PostgreSQL through SQLAlchemy and Alembic; private file storage with randomised names; ChromaDB for vectors."],
  ["Models", "Configurable OpenAI-compatible, Anthropic or Ollama providers with fallback. Unavailable providers are reported, never simulated."],
];

export default function Architecture() {
  const q = useQuery({ queryKey: ["agents"], queryFn: () => api<AgentsRes>("/api/system/agents") });
  const status = useQuery({ queryKey: ["sysstatus"], queryFn: () => api<Record<string, unknown>>("/api/system/status") });
  const [sel, setSel] = useState<string | undefined>(undefined);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const agents = q.data!.agents;
  const a = agents.find((x) => x.id === sel);
  return (
    <div className="space-y-6">
      <PageHeader title="System Architecture" description="Smart AI Hiring Assistant Using Multi-Agent LLMs and Retrieval-Augmented Generation. Select a node to read its contract and live status." />
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Agent map" subtitle="Inner ring: screening pipeline in execution order. Outer arc: assurance services that run apart from scoring.">
          <AgentScene agents={agents} interactive selected={sel} onSelect={setSel} height={440} running={q.data!.latest_run?.status === "running"} />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {agents.map((x) => <button key={x.id} onClick={() => setSel(x.id)} className={`rounded-control border px-2 py-0.5 text-xs ${sel === x.id ? "border-cyan text-cyan" : "border-line text-muted"}`}>{x.number}. {x.name}</button>)}
          </div>
        </Panel>
        <Panel title={a ? `${a.number}. ${a.name}` : "Agent details"}>
          {!a ? <p className="text-sm text-muted">Select a node or a name.</p> : (
            <div className="space-y-3 text-sm">
              <p>{a.responsibility}</p>
              <p className="text-muted">{a.implementation}</p>
              <p><StatusBadge s={a.availability} /> <span className="text-muted">{a.availability_detail}</span></p>
              <div><p className="font-medium">Input</p><pre className="font-mono text-xs">{JSON.stringify(a.input, null, 2)}</pre></div>
              <div><p className="font-medium">Output</p><pre className="font-mono text-xs">{JSON.stringify(a.output, null, 2)}</pre></div>
              <p><span className="font-medium">Tools:</span> {a.tools.length ? a.tools.map((t) => <Badge key={t}>{t}</Badge>) : "none"}</p>
              <p><span className="font-medium">Access:</span> <span className="text-muted">{a.access}</span></p>
            </div>
          )}
        </Panel>
      </div>
      <Panel title="Layers">
        <dl className="grid gap-4 md:grid-cols-2">{LAYERS.map(([t, d]) => <div key={t}><dt className="font-medium">{t}</dt><dd className="text-sm text-muted">{d}</dd></div>)}</dl>
      </Panel>
      <Panel title="Runtime configuration" subtitle="Read from the running server.">
        {status.data ? <pre className="overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(status.data, null, 2)}</pre> : <Loading />}
      </Panel>
    </div>
  );
}
