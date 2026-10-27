import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, TaskBar, Td } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { pct, short, when } from "../lib/format";
import { useTask } from "../lib/hooks";

type Run = { id: string; suite_version: string; status: string; summary: { attempts: number; successes: number; attack_success_rate: number | null; by_category: Record<string, { attempts: number; successes: number; detected: number; success_rate: number | null }>; skipped: number; note: string } | null; error: string | null; created_at: string;
  results?: { category: string; test: string; attack_succeeded?: boolean; detected?: boolean; status?: string; detail: string; path?: string }[] };

export default function Security() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["secruns"], queryFn: () => api<Run[]>("/api/security/runs"), enabled: can("admin", "researcher") });
  const evals = useQuery({ queryKey: ["runs"], queryFn: () => api<{ id: string; job_title: string; status: string; created_at: string }[]>("/api/evaluations") });
  const [runId, setRunId] = useState("");
  const [sample, setSample] = useState(5);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const task = useTask(taskId);
  const detail = useQuery({ queryKey: ["secrun", open, task.data?.status], enabled: !!open, queryFn: () => api<Run>(`/api/security/runs/${open}`) });
  const start = useMutation({ mutationFn: () => api<{ security_run_id: string; task_id: string }>("/api/security/runs", { method: "POST", json: { run_id: runId || null, sample } }),
    onSuccess: (r) => { setTaskId(r.task_id); setOpen(r.security_run_id); qc.invalidateQueries({ queryKey: ["secruns"] }); } });
  if (!can("admin", "researcher")) return <div><PageHeader title="Security and Robustness" /><p className="text-sm text-muted">Available to administrators and researchers.</p></div>;
  return (
    <div className="space-y-6">
      <PageHeader title="Security and Robustness" description="A defined test suite for prompt injection, malformed files, invalid model output, cross-candidate leakage, workspace isolation and permissions. Every outcome is measured." />
      <Panel title="Controls in place">
        <ul className="grid gap-2 text-sm text-muted md:grid-cols-2">
          <li>Resume text is wrapped in randomised untrusted-data markers, separate from system instructions.</li>
          <li>Model output must pass a strict schema; out-of-range ratings and quote-less claims are rejected.</li>
          <li>Every citation is checked against the stored text of the same resume.</li>
          <li>File type checked by content, size limits, encrypted and malformed files refused.</li>
          <li>No tool definitions are sent to the model; it has no tools to call.</li>
          <li>Server-side role checks, workspace filters on every query, rate limits and an audit log.</li>
        </ul>
      </Panel>
      <Panel title="Run the suite" subtitle="Choose a completed evaluation run so injection payloads are tested against its real resumes and rubric.">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Evaluation run"><Select value={runId} onChange={(e) => setRunId(e.target.value)} options={[{ value: "", label: "None (file, validator and permission tests only)" }, ...(evals.data ?? []).filter((r) => r.status === "completed").map((r) => ({ value: r.id, label: `${r.job_title} (${when(r.created_at)})` }))]} /></Field>
          <Field label="Resumes to attack"><Input type="number" min={1} max={50} value={sample} onChange={(e) => setSample(Number(e.target.value))} /></Field>
        </div>
        <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={start.error} /></div>
        <Button className="mt-3" onClick={() => start.mutate()} loading={start.isPending}>Run security suite</Button>
      </Panel>
      <Panel title="Runs">
        {runs.isLoading ? <Loading /> : !runs.data?.length ? <Empty title="The suite has not been run" /> : (
          <Table head={["Run", "Suite", "Status", "Attempts", "Successful attacks", "Attack success rate", "Created", ""]}>
            {runs.data.map((r) => <tr key={r.id}><Td mono>{short(r.id)}</Td><Td>{r.suite_version}</Td><Td><StatusBadge s={r.status} /></Td><Td>{r.summary?.attempts ?? "—"}</Td><Td>{r.summary?.successes ?? "—"}</Td><Td>{pct(r.summary?.attack_success_rate)}</Td><Td>{when(r.created_at)}</Td><Td><Button variant="ghost" onClick={() => setOpen(r.id)}>Open</Button></Td></tr>)}
          </Table>
        )}
      </Panel>
      {open && detail.data && (
        <Panel title={`Results for run ${short(open)}`} subtitle={detail.data.summary?.note}>
          {detail.data.error && <ErrorNote error={detail.data.error} />}
          {detail.data.summary && (
            <div className="mb-4 grid gap-2 sm:grid-cols-3">
              {Object.entries(detail.data.summary.by_category).map(([k, v]) => (
                <div key={k} className="rounded-control border border-line px-3 py-2 text-sm"><p className="font-medium">{k.replace(/_/g, " ")}</p>
                  <p className="text-muted">{v.successes} of {v.attempts} succeeded{v.detected ? `, ${v.detected} detected` : ""}</p></div>
              ))}
            </div>
          )}
          <Table head={["Category", "Test", "Outcome", "Detected", "Detail"]}>
            {(detail.data.results ?? []).map((r, i) => (
              <tr key={i}><Td>{r.category.replace(/_/g, " ")}</Td><Td>{r.test}</Td>
                <Td>{r.status === "skipped" ? <Badge color="amber">skipped</Badge> : r.attack_succeeded ? <Badge color="danger">attack succeeded</Badge> : <Badge color="ok">blocked</Badge>}</Td>
                <Td>{r.detected === undefined ? "—" : r.detected ? "yes" : "no"}</Td><Td className="text-muted">{r.detail}</Td></tr>
            ))}
          </Table>
        </Panel>
      )}
    </div>
  );
}
