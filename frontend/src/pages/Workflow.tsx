import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Badge, ErrorNote, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td } from "../components/ui";
import { api } from "../lib/api";
import { when } from "../lib/format";

export type AgentDef = { id: string; number: number; name: string; responsibility: string; implementation: string; input: Record<string, string>; output: Record<string, string>; tools: string[]; access: string; availability: string; availability_detail: string };
export type AgentsRes = { agents: AgentDef[]; orchestrator: string; pipeline_order: string[]; latest_run: { id: string; status: string } | null };
type Trace = { trace_id: string; orchestrator: string; status: string; error: string | null; events: { seq: number; agent: string; status: string; duration_ms: number; detail: string; error: string | null; output_summary: Record<string, unknown> }[] };

export default function Workflow() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run") ?? "";
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => api<AgentsRes>("/api/system/agents") });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<{ id: string; job_title: string; created_at: string; status: string }[]>("/api/evaluations") });
  const trace = useQuery({ queryKey: ["trace", runId], enabled: !!runId, queryFn: () => api<Trace>(`/api/evaluations/${runId}/trace`),
    refetchInterval: (s) => (s.state.data && ["queued", "running"].includes(s.state.data.status) ? 2000 : false) });
  return (
    <div className="space-y-6">
      <PageHeader title="Multi-Agent Workflow" description="What each agent does, how it is implemented, and what actually ran in a given evaluation." />
      <Panel title="Execution trace" subtitle="Recorded per run. Skipped and failed stages are shown as they happened."
        actions={<Select aria-label="Evaluation run" value={runId} onChange={(e) => setParams(e.target.value ? { run: e.target.value } : {})}
          options={[{ value: "", label: "Choose an evaluation run" }, ...(runs.data ?? []).map((r) => ({ value: r.id, label: `${r.job_title} (${when(r.created_at)})` }))]} />}>
        {!runId ? <p className="text-sm text-muted">Pick a run to see its trace.</p> : trace.isLoading ? <Loading /> : trace.error ? <ErrorNote error={trace.error} /> : (
          <>
            <p className="mb-3 text-sm">Orchestrator: <span className="font-medium">{trace.data!.orchestrator || "not recorded"}</span>. Trace <span className="font-mono text-xs">{trace.data!.trace_id}</span>.</p>
            {trace.data!.error && <ErrorNote error={trace.data!.error} />}
            <ol className="space-y-2">
              {trace.data!.events.map((e) => (
                <li key={e.seq} className="flex flex-wrap items-start gap-3 rounded-control border border-line p-3 text-sm">
                  <span className="w-6 text-muted tabular-nums">{e.seq + 1}</span>
                  <span className="min-w-[14rem] font-medium">{e.agent.replace(/_/g, " ")}</span>
                  <StatusBadge s={e.status} />
                  <span className="text-muted">{e.duration_ms} ms</span>
                  <span className="flex-1 text-muted">{e.detail}</span>
                  {e.error && <pre className="w-full whitespace-pre-wrap font-mono text-xs text-danger">{e.error}</pre>}
                </li>
              ))}
            </ol>
            {!trace.data!.events.length && <p className="text-sm text-muted">No stages were recorded yet.</p>}
          </>
        )}
      </Panel>
      <Panel title="Agents and services" subtitle={`Configured orchestrator: ${agents.data?.orchestrator ?? "…"}`}>
        {agents.isLoading ? <Loading /> : agents.error ? <ErrorNote error={agents.error} /> : (
          <Table head={["#", "Agent", "Responsibility", "Implementation", "Availability", "Tools", "Access"]}>
            {agents.data!.agents.map((a) => (
              <tr key={a.id}><Td>{a.number}</Td><Td className="font-medium">{a.name}</Td><Td className="text-muted">{a.responsibility}</Td><Td className="text-muted">{a.implementation}</Td>
                <Td><StatusBadge s={a.availability} /><div className="mt-1 text-xs text-muted">{a.availability_detail}</div></Td>
                <Td>{a.tools.length ? a.tools.map((t) => <Badge key={t}>{t}</Badge>) : "none"}</Td><Td className="text-muted">{a.access}</Td></tr>
            ))}
          </Table>
        )}
      </Panel>
    </div>
  );
}
