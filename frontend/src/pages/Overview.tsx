import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AgentScene, type AgentNode } from "../components/Scene3D";
import { Badge, Empty, ErrorNote, Loading, PageHeader, Panel, Stat, StatusBadge, Table, Td } from "../components/ui";
import { api } from "../lib/api";
import { fmt, when } from "../lib/format";

type Dash = {
  counts: Record<string, number>;
  datasets: { id: string; name: string; status: string; validation: { rejected?: number; errors?: string[] } | null; revision: string; imported_at: string | null; split_config: unknown }[];
  latest_experiments: { id: string; experiment_id: string; split: string; status: string; metrics: { "ndcg@10"?: { mean: number | null } } | null; created_at: string }[];
  latest_audits: { id: string; status: string; summary: Record<string, unknown> | null; created_at: string; kind?: string }[];
  recent_tasks: { id: string; kind: string; status: string; message: string; error: string | null; created_at: string }[];
  config: { llm: { configured: boolean; provider: string; model: string; note: string | null }; models: Record<string, unknown>; orchestrator: string };
};

export default function Overview() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 10000 });
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => api<{ agents: (AgentNode & { availability: string })[]; latest_run: { status: string } | null }>("/api/system/agents") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const d = q.data!;
  const c = d.counts;
  const total = c.synthetic_resumes + c.genuine_resumes + c.synthetic_jobs + c.genuine_jobs;
  const chart = [
    { name: "Resumes", synthetic: c.synthetic_resumes, genuine: c.genuine_resumes },
    { name: "Job descriptions", synthetic: c.synthetic_jobs, genuine: c.genuine_jobs },
  ];
  return (
    <div className="space-y-6">
      <PageHeader title="Overview" description="Live counts and status from this workspace's database." />
      {total === 0 && (
        <Empty title="No data available yet" action={<Link className="text-sm text-cyan" to="/app/datasets">Go to Dataset Management</Link>}>
          Import the public synthetic research dataset on the Dataset Management page, or add genuine job descriptions and resumes with consent records.
        </Empty>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Synthetic resumes" value={c.synthetic_resumes.toLocaleString()} note="research dataset" />
        <Stat label="Synthetic jobs" value={c.synthetic_jobs.toLocaleString()} note="research dataset" />
        <Stat label="Matching records" value={c.matching_records.toLocaleString()} note="published labels" />
        <Stat label="Genuine resumes" value={c.genuine_resumes.toLocaleString()} note={`${c.genuine_jobs} genuine jobs`} />
        <Stat label="Completed evaluations" value={c.completed_evaluations} />
        <Stat label="Pending human reviews" value={c.pending_reviews} note={c.pending_reviews ? <Link className="text-cyan" to="/app/evidence">Open review queue</Link> : undefined} />
        <Stat label="Failed background tasks" value={c.failed_tasks} />
        <Stat label="Orchestrator" value={<span className="text-base">{d.config.orchestrator}</span>} note={d.config.llm.configured ? `LLM ${d.config.llm.provider}/${d.config.llm.model}` : "No LLM configured"} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Panel title="Agent status" subtitle="Node colour shows real availability. Particles scale with the stored resume count.">
          {agents.data ? (
            <AgentScene agents={agents.data.agents} documents={c.synthetic_resumes + c.genuine_resumes} running={agents.data.latest_run?.status === "running"} height={300} />
          ) : <Loading />}
          <div className="mt-2 flex flex-wrap gap-2 text-xs"><Badge color="cyan">available</Badge><Badge color="amber">partial</Badge><Badge color="danger">unavailable</Badge></div>
        </Panel>
        <Panel title="Records by source">
          {total === 0 ? <p className="text-sm text-muted">Nothing to chart yet.</p> : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" />
                  <XAxis dataKey="name" stroke="rgb(var(--muted))" fontSize={12} />
                  <YAxis stroke="rgb(var(--muted))" fontSize={12} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--line))" }} />
                  <Bar dataKey="synthetic" fill="rgb(var(--violet))" name="Synthetic research" />
                  <Bar dataKey="genuine" fill="rgb(var(--cyan))" name="Genuine" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Datasets">
          {d.datasets.length === 0 ? <p className="text-sm text-muted">No dataset versions yet.</p> : (
            <Table head={["Name", "Status", "Rejected", "Split", "Imported"]}>
              {d.datasets.map((v) => (
                <tr key={v.id}><Td>{v.name}</Td><Td><StatusBadge s={v.status} /></Td><Td>{v.validation?.rejected ?? "—"}</Td>
                  <Td>{v.split_config ? "created" : "not yet"}</Td><Td>{when(v.imported_at)}</Td></tr>
              ))}
            </Table>
          )}
        </Panel>
        <Panel title="Latest experiment runs">
          {d.latest_experiments.length === 0 ? <p className="text-sm text-muted">No experiments have been run.</p> : (
            <Table head={["Exp.", "Split", "Status", "nDCG@10", "Started"]}>
              {d.latest_experiments.map((e) => (
                <tr key={e.id}><Td>{e.experiment_id}</Td><Td>{e.split}</Td><Td><StatusBadge s={e.status} /></Td>
                  <Td>{fmt(e.metrics?.["ndcg@10"]?.mean ?? null)}</Td><Td>{when(e.created_at)}</Td></tr>
              ))}
            </Table>
          )}
        </Panel>
        <Panel title="Latest audit runs">
          {d.latest_audits.length === 0 ? <p className="text-sm text-muted">No fairness or security audits yet.</p> : (
            <Table head={["Type", "Status", "Started"]}>
              {d.latest_audits.map((a) => <tr key={a.id}><Td>{a.kind === "security" ? "Security" : "Fairness"}</Td><Td><StatusBadge s={a.status} /></Td><Td>{when(a.created_at)}</Td></tr>)}
            </Table>
          )}
        </Panel>
        <Panel title="Background tasks">
          {d.recent_tasks.length === 0 ? <p className="text-sm text-muted">No tasks yet.</p> : (
            <Table head={["Task", "Status", "Message", "Started"]}>
              {d.recent_tasks.map((t) => <tr key={t.id}><Td>{t.kind}</Td><Td><StatusBadge s={t.status} /></Td><Td className="max-w-xs truncate text-muted">{t.error ? t.error.split("\n")[0] : t.message}</Td><Td>{when(t.created_at)}</Td></tr>)}
            </Table>
          )}
        </Panel>
      </div>
      {!d.config.llm.configured && <p className="text-sm text-muted">{d.config.llm.note}</p>}
    </div>
  );
}
