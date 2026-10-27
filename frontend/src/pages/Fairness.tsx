import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, TaskBar, Td } from "../components/ui";
import { api, download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ci, fmt, short, when } from "../lib/format";
import { useTask } from "../lib/hooks";

type Audit = { id: string; run_id: string; status: string; summary: Record<string, unknown> | null; error: string | null; created_at: string; results?: Record<string, unknown>[] };
type TestRow = { resume_id: string; original: string; replacement: string; group: string };

export default function Fairness() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const audits = useQuery({ queryKey: ["audits"], queryFn: () => api<Audit[]>("/api/fairness/audits"), enabled: can("admin", "researcher") });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<{ id: string; job_title: string; status: string; corpus: string; created_at: string }[]>("/api/evaluations") });
  const [runId, setRunId] = useState("");
  const run = useQuery({ queryKey: ["run", runId], enabled: !!runId, queryFn: () => api<{ corpus: string; results: { resume_id: string; display_ref: string; final_rank: number }[] }>(`/api/evaluations/${runId}`) });
  const [tests, setTests] = useState<TestRow[]>([]);
  const [tol, setTol] = useState(0);
  const [authorized, setAuthorized] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const task = useTask(taskId);
  const detail = useQuery({ queryKey: ["audit", open, task.data?.status], enabled: !!open, queryFn: () => api<Audit>(`/api/fairness/audits/${open}`) });
  const start = useMutation({
    mutationFn: () => api<{ audit_id: string; task_id: string }>("/api/fairness/audits", { method: "POST", json: { run_id: runId, tolerance: tol, authorized,
      tests: tests.map((t) => ({ ...t, group: t.group || null })) } }),
    onSuccess: (r) => { setTaskId(r.task_id); setOpen(r.audit_id); qc.invalidateQueries({ queryKey: ["audits"] }); },
  });
  if (!can("admin", "researcher")) return <div><PageHeader title="Fairness Audit" /><p className="text-sm text-muted">Fairness audits are available to administrators and researchers.</p></div>;
  const completed = (runs.data ?? []).filter((r) => r.status === "completed");
  return (
    <div className="space-y-6">
      <PageHeader title="Fairness Audit Center" description="Controlled counterfactual tests: change one job-irrelevant token, such as a name, keep everything else, and rerun the same pipeline." />
      <p className="text-sm text-muted">Results apply only to the substitutions you test. They do not show that the system is fair. Protected characteristics are never inferred from names or text.</p>
      <Panel title="New audit">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Completed evaluation run"><Select value={runId} onChange={(e) => { setRunId(e.target.value); setTests([]); }} options={[{ value: "", label: "Choose a run" }, ...completed.map((r) => ({ value: r.id, label: `${r.job_title} (${when(r.created_at)})` }))]} /></Field>
          <Field label="Flag score changes above" hint="0 flags any change."><Input type="number" min={0} max={1} step={0.01} value={tol} onChange={(e) => setTol(Number(e.target.value))} /></Field>
          {run.data?.corpus === "genuine" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} />Testing these genuine records is authorized</label>}
        </div>
        {runId && (
          <div className="mt-4 space-y-2">
            <p className="text-sm font-medium">Substitutions</p>
            <p className="text-xs text-muted">Enter the exact text that appears in the resume (for example the candidate's name as written) and its replacement. The optional group label is your own label for the replacement, used only for per-group summaries.</p>
            {tests.map((t, i) => (
              <div key={i} className="grid gap-2 md:grid-cols-[1.2fr_1fr_1fr_0.8fr_auto]">
                <Select aria-label="Resume" value={t.resume_id} onChange={(e) => setTests(tests.map((x, k) => (k === i ? { ...x, resume_id: e.target.value } : x)))} options={(run.data?.results ?? []).map((c) => ({ value: c.resume_id, label: `#${c.final_rank} ${c.display_ref}` }))} />
                <Input aria-label="Original token" placeholder="Original text" value={t.original} onChange={(e) => setTests(tests.map((x, k) => (k === i ? { ...x, original: e.target.value } : x)))} />
                <Input aria-label="Replacement" placeholder="Replacement" value={t.replacement} onChange={(e) => setTests(tests.map((x, k) => (k === i ? { ...x, replacement: e.target.value } : x)))} />
                <Input aria-label="Group label" placeholder="Group label (optional)" value={t.group} onChange={(e) => setTests(tests.map((x, k) => (k === i ? { ...x, group: e.target.value } : x)))} />
                <Button variant="quiet" onClick={() => setTests(tests.filter((_, k) => k !== i))}>Remove</Button>
              </div>
            ))}
            <Button variant="ghost" onClick={() => setTests([...tests, { resume_id: run.data?.results[0]?.resume_id ?? "", original: "", replacement: "", group: "" }])} disabled={!run.data?.results.length}>Add substitution</Button>
          </div>
        )}
        <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={start.error} /></div>
        <Button className="mt-3" onClick={() => start.mutate()} loading={start.isPending} disabled={!tests.length || tests.some((t) => !t.original || !t.replacement || !t.resume_id)}>Run audit</Button>
      </Panel>
      <Panel title="Audits">
        {audits.isLoading ? <Loading /> : !audits.data?.length ? <Empty title="No audits have been run" /> : (
          <Table head={["Audit", "Status", "Tests", "Mean |ΔS|", "Rank flip rate", "Flagged", "Created", ""]}>
            {audits.data.map((a) => {
              const s = (a.summary ?? {}) as Record<string, number | null>;
              return <tr key={a.id}><Td mono>{short(a.id)}</Td><Td><StatusBadge s={a.status} /></Td><Td>{s.tests_completed ?? "—"}</Td><Td>{fmt(s.mean_abs_counterfactual_score_gap)}</Td><Td>{fmt(s.counterfactual_rank_flip_rate)}</Td><Td>{s.flagged ?? "—"}</Td><Td>{when(a.created_at)}</Td>
                <Td><Button variant="ghost" onClick={() => setOpen(a.id)}>Open</Button></Td></tr>;
            })}
          </Table>
        )}
      </Panel>
      {open && detail.data && (
        <Panel title={`Audit ${short(open)}`} actions={<Button variant="ghost" onClick={() => download(`/api/fairness/audits/${open}/export.csv`, `fairness-${short(open)}.csv`)}>Export CSV</Button>}>
          {detail.data.error && <ErrorNote error={detail.data.error} />}
          {detail.data.summary && (
            <div className="mb-4 text-sm">
              <p>Mean absolute counterfactual score gap: <b>{fmt(detail.data.summary.mean_abs_counterfactual_score_gap as number)}</b> (95% CI {ci(detail.data.summary.mean_abs_gap_ci95 as number[])})</p>
              <p>Counterfactual rank flip rate: <b>{fmt(detail.data.summary.counterfactual_rank_flip_rate as number)}</b></p>
              <p className="text-muted">{String(detail.data.summary.worst_group_note)}</p>
              <p className="text-muted">{String(detail.data.summary.limitation)}</p>
            </div>
          )}
          <Table head={["Resume", "Original", "Replacement", "Status", "S before", "S after", "|ΔS|", "Rank", "Flip rate", ""]}>
            {(detail.data.results ?? []).map((r, i) => (
              <tr key={i}><Td mono>{short(String(r.resume_id))}</Td><Td>{String(r.original)}</Td><Td>{String(r.replacement)}</Td><Td><StatusBadge s={String(r.status)} /></Td>
                <Td>{fmt(r.score_original as number)}</Td><Td>{fmt(r.score_counterfactual as number)}</Td><Td>{fmt(r.abs_gap as number)}</Td>
                <Td>{String(r.rank_original ?? "—")} to {String(r.rank_counterfactual ?? "—")}</Td><Td>{fmt(r.pairwise_flip_rate as number)}</Td>
                <Td>{r.flagged ? <Badge color="amber">flagged</Badge> : r.error ? <span className="text-xs text-danger">{String(r.error)}</span> : null}</Td></tr>
            ))}
          </Table>
        </Panel>
      )}
    </div>
  );
}
