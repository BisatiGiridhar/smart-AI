import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CorpusPicker } from "../components/CorpusPicker";
import { Badge, Button, DecisionNotice, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, TaskBar, Td } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmt, pct, when } from "../lib/format";
import { useTask } from "../lib/hooks";
import type { Rubric } from "../lib/types";
import { JobPicker } from "./Search";

type RunRow = { id: string; job_id: string; job_title: string; rubric_version: number; corpus: string; status: string; orchestrator: string; created_at: string; candidates: number; error: string | null };
type Cand = { id: string; resume_id: string; display_ref: string; final_rank: number; bm25_rank: number | null; dense_rank: number | null; rrf_rank: number | null; rerank_score: number | null; score: number | null; coverage: number | null; s_low: number | null; s_high: number | null; review_status: string; verified: string[]; unverified: string[]; insufficient_evidence: boolean; review_reasons: string[]; skills_matched: string[]; gaps: string[]; created_at: string };
type RunDetail = RunRow & { config: Record<string, unknown>; model_info: Record<string, unknown>; retrieval: Record<string, unknown> | null; rubric: { version: number; origin: string; criteria: { id: string; label: string }[] }; results: Cand[]; notice: string; finished_at: string | null };

export default function Ranking() {
  const { runId } = useParams();
  return runId ? <RunView id={runId} /> : <RunList />;
}

function RunList() {
  const { can } = useAuth();
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<RunRow[]>("/api/evaluations"), refetchInterval: 5000 });
  return (
    <div className="space-y-6">
      <PageHeader title="Candidate Ranking" description="Run the full multi-agent pipeline for a job and an approved rubric, then compare candidates criterion by criterion." />
      <DecisionNotice />
      {can("admin", "recruiter", "researcher") && <StartRun />}
      <Panel title="Evaluation runs">
        {runs.isLoading ? <Loading /> : runs.error ? <ErrorNote error={runs.error} /> : !runs.data?.length ? <Empty title="No evaluation runs yet">Choose a job with an approved rubric above.</Empty> : (
          <Table head={["Job", "Rubric", "Corpus", "Status", "Candidates", "Orchestrator", "Started"]}>
            {runs.data.map((r) => (
              <tr key={r.id}><Td><Link className="text-cyan hover:underline" to={`/app/ranking/${r.id}`}>{r.job_title}</Link></Td><Td>v{r.rubric_version}</Td>
                <Td>{r.corpus === "genuine" ? "genuine" : <Badge color="violet">synthetic</Badge>}</Td><Td><StatusBadge s={r.status} /></Td><Td>{r.candidates}</Td><Td>{r.orchestrator || "—"}</Td><Td>{when(r.created_at)}</Td></tr>
            ))}
          </Table>
        )}
      </Panel>
    </div>
  );
}

function StartRun() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [corpus, setCorpus] = useState("genuine");
  const [jobId, setJobId] = useState("");
  const [rubricId, setRubricId] = useState("");
  const [shortlist, setShortlist] = useState(50);
  const [policy, setPolicy] = useState("normalized_verified_score");
  const [evaluator, setEvaluator] = useState("deterministic");
  const [threshold, setThreshold] = useState(0.5);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const task = useTask(taskId);
  const job = useQuery({ queryKey: ["job", jobId], enabled: !!jobId, queryFn: () => api<{ rubrics: Rubric[] }>(`/api/jobs/${jobId}`) });
  const approved = (job.data?.rubrics ?? []).filter((r) => r.status === "approved");
  useEffect(() => { setRubricId(approved[0]?.id ?? ""); }, [jobId, job.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (task.data?.status === "succeeded" && runId) { qc.invalidateQueries({ queryKey: ["runs"] }); nav(`/app/ranking/${runId}`); } }, [task.data, runId, nav, qc]);
  const start = useMutation({
    mutationFn: () => api<{ run_id: string; task_id: string }>("/api/evaluations", { method: "POST", json: { job_id: jobId, rubric_id: rubricId, corpus,
      config: { shortlist_size: shortlist, ranking_policy: policy, evaluator, coverage_threshold: threshold } } }),
    onSuccess: (r) => { setTaskId(r.task_id); setRunId(r.run_id); },
  });
  return (
    <Panel title="Start an evaluation run">
      <div className="grid gap-3 md:grid-cols-3">
        <CorpusPicker value={corpus} onChange={(v) => { setCorpus(v); setJobId(""); }} />
        <JobPicker corpus={corpus} value={jobId} onChange={setJobId} />
        <Field label="Approved rubric" hint={jobId && !approved.length ? "This job has no approved rubric. Approve one on its job page." : undefined}>
          <Select value={rubricId} onChange={(e) => setRubricId(e.target.value)} options={approved.length ? approved.map((r) => ({ value: r.id, label: `Version ${r.version}` })) : [{ value: "", label: "None" }]} />
        </Field>
        <Field label="Shortlist evaluated"><Input type="number" min={1} max={500} value={shortlist} onChange={(e) => setShortlist(Number(e.target.value))} /></Field>
        <Field label="Ranking policy"><Select value={policy} onChange={(e) => setPolicy(e.target.value)} options={[{ value: "normalized_verified_score", label: "Normalized verified score S" }, { value: "lower_bound", label: "Lower bound S_low (penalises missing evidence)" }]} /></Field>
        <Field label="Evaluator"><Select value={evaluator} onChange={(e) => setEvaluator(e.target.value)} options={[{ value: "deterministic", label: "Deterministic evidence matching" }, { value: "llm", label: "LLM with schema validation" }]} /></Field>
        <Field label="Review if coverage below"><Input type="number" min={0} max={1} step={0.05} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></Field>
      </div>
      <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={start.error} /></div>
      <Button className="mt-3" onClick={() => start.mutate()} loading={start.isPending || task.data?.status === "running"} disabled={!rubricId}>Run evaluation</Button>
    </Panel>
  );
}

function RunView({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["run", id], queryFn: () => api<RunDetail>(`/api/evaluations/${id}`), refetchInterval: (s) => (s.state.data && ["queued", "running"].includes(s.state.data.status) ? 2000 : false) });
  const [compare, setCompare] = useState<string[]>([]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const r = q.data!;
  const toggle = (cid: string) => setCompare((c) => (c.includes(cid) ? c.filter((x) => x !== cid) : [...c, cid].slice(-3)));
  const chosen = r.results.filter((c) => compare.includes(c.id));
  return (
    <div className="space-y-6">
      <PageHeader title={`Ranking for ${r.job_title}`} description={<><Link className="text-cyan" to="/app/ranking">All runs</Link>. Rubric v{r.rubric.version} ({r.rubric.origin === "auto_draft" ? "auto-drafted, then approved" : "recruiter"}). Corpus {r.corpus === "genuine" ? "genuine" : "synthetic research"}.</>}
        actions={<Link to={`/app/workflow?run=${r.id}`} className="rounded-control border border-line px-3 py-2 text-sm hover:bg-raised">View agent trace</Link>} />
      <p className="text-sm text-muted">{r.notice}</p>
      {r.error && <ErrorNote error={r.error} />}
      <Panel title="Ranked candidates" subtitle="Select up to three to compare. Retrieval and rerank values are not candidate merit." actions={<StatusBadge s={r.status} />}>
        {!r.results.length ? <p className="text-sm text-muted">{["queued", "running"].includes(r.status) ? "The run is in progress." : "No candidates were ranked."}</p> : (
          <Table head={["", "Rank", "Candidate", "S", "Coverage", "Bounds", "Verified", "Unverified", "BM25 / dense / RRF", "Rerank", "Matches", "Gaps", "Review"]}>
            {r.results.map((c) => (
              <tr key={c.id}>
                <Td><input type="checkbox" aria-label={`Compare ${c.display_ref}`} checked={compare.includes(c.id)} onChange={() => toggle(c.id)} /></Td>
                <Td>{c.final_rank}</Td>
                <Td><Link className="text-cyan hover:underline" to={`/app/evidence/${c.id}`}>{c.display_ref}</Link></Td>
                <Td>{c.insufficient_evidence ? <Badge color="amber">insufficient evidence</Badge> : fmt(c.score)}</Td>
                <Td>{pct(c.coverage)}</Td><Td className="whitespace-nowrap">{fmt(c.s_low, 2)}–{fmt(c.s_high, 2)}</Td>
                <Td>{c.verified.length}</Td><Td>{c.unverified.length}</Td>
                <Td className="whitespace-nowrap">{c.bm25_rank ?? "—"} / {c.dense_rank ?? "—"} / {c.rrf_rank ?? "—"}</Td><Td>{fmt(c.rerank_score)}</Td>
                <Td className="max-w-[14rem] text-muted">{c.skills_matched.join(", ") || "—"}</Td><Td className="max-w-[14rem] text-muted">{c.gaps.join(", ") || "—"}</Td>
                <Td><StatusBadge s={c.review_status} /></Td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
      {chosen.length >= 2 && (
        <Panel title="Side-by-side comparison" subtitle="Same rubric version for every candidate.">
          <Table head={["Criterion", ...chosen.map((c) => c.display_ref)]}>
            {r.rubric.criteria.map((cr) => (
              <tr key={cr.id}><Td>{cr.label}</Td>{chosen.map((c) => <Td key={c.id}>{c.verified.includes(cr.id) ? <Badge color="ok">verified</Badge> : <Badge>no verified evidence</Badge>}</Td>)}</tr>
            ))}
            <tr><Td>Score S</Td>{chosen.map((c) => <Td key={c.id}>{fmt(c.score)}</Td>)}</tr>
            <tr><Td>Coverage</Td>{chosen.map((c) => <Td key={c.id}>{pct(c.coverage)}</Td>)}</tr>
            <tr><Td>Review reasons</Td>{chosen.map((c) => <Td key={c.id} className="text-muted">{c.review_reasons.join("; ") || "none"}</Td>)}</tr>
          </Table>
        </Panel>
      )}
      <Panel title="Reproducibility record">
        <div className="grid gap-3 md:grid-cols-3">
          {[["Configuration", r.config], ["Models", r.model_info], ["Retrieval", r.retrieval]].map(([t, v]) => (
            <div key={t as string}><p className="mb-1 text-sm font-medium">{t as string}</p><pre className="max-h-64 overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(v, null, 2)}</pre></div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
