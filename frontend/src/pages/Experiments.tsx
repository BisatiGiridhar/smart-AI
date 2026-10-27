import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, SyntheticNotice, Table, TaskBar, Td } from "../components/ui";
import { api, download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ci, fmt, short, when } from "../lib/format";
import { useDatasets, useTask } from "../lib/hooks";

type Def = { id: string; name: string; description: string; requires_llm?: boolean; requires_dense?: boolean; requires_rerank?: boolean };
type Agg = { mean: number | null; ci95: number[] | null; n: number };
type Exp = { id: string; experiment_id: string; split: string; status: string; error: string | null; created_at: string; config: Record<string, unknown>;
  metrics: (Record<string, unknown> & { "ndcg@10"?: Agg; mrr?: Agg; pearson?: number | null; spearman?: number | null; mae?: number | null; rmse?: number | null; jobs_evaluated?: number; p95_seconds_per_job?: number | null; cost_per_resume_usd?: number | null; attack?: Record<string, { attempts: number; successes: number; success_rate: number | null; detection_rate: number | null }> }) | null;
  test_conditions: Record<string, unknown> };

export default function Experiments() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const defs = useQuery({ queryKey: ["expdefs"], queryFn: () => api<Def[]>("/api/experiments/definitions") });
  const exps = useQuery({ queryKey: ["exps"], queryFn: () => api<Exp[]>("/api/experiments/runs"), refetchInterval: 5000 });
  const ds = useDatasets();
  const ready = (ds.data?.versions ?? []).filter((v) => v.status === "imported" && v.split_config);
  const [f, setF] = useState({ experiment_id: "G", dataset_version_id: "", split: "test", max_jobs: 100, negatives_per_job: 30, relevance_threshold: 0.5, k: 10, seed: 42, shortlist_size: 10, evaluator: "deterministic" });
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId);
  const [open, setOpen] = useState<string | null>(null);
  const [cmp, setCmp] = useState({ a: "", b: "" });
  const start = useMutation({
    mutationFn: () => api<{ task_id: string }>("/api/experiments/runs", { method: "POST", json: { experiment_id: f.experiment_id, dataset_version_id: f.dataset_version_id || ready[0]?.id, split: f.split,
      max_jobs: f.max_jobs, negatives_per_job: f.negatives_per_job, relevance_threshold: f.relevance_threshold, k: f.k, seed: f.seed,
      pipeline: { shortlist_size: f.shortlist_size, evaluator: f.evaluator } } }),
    onSuccess: (r) => { setTaskId(r.task_id); qc.invalidateQueries({ queryKey: ["exps"] }); },
  });
  const compare = useQuery({ queryKey: ["cmp", cmp.a, cmp.b], enabled: !!cmp.a && !!cmp.b && cmp.a !== cmp.b, queryFn: () => api<{ paired_jobs: number; wilcoxon: { statistic: number; p_value: number; n: number; note?: string } | null }>(`/api/experiments/compare?a=${cmp.a}&b=${cmp.b}`) });
  const detail = exps.data?.find((e) => e.id === open);
  const set = (k: keyof typeof f, v: string | number) => setF({ ...f, [k]: v });
  const doneRuns = (exps.data ?? []).filter((e) => e.status === "completed");
  return (
    <div className="space-y-6">
      <PageHeader title="Research Experiment Lab" description="Ten controlled configurations on identical splits, pools, rubrics and seeds. Only the factor under test changes." actions={<Button variant="ghost" onClick={() => download("/api/reports/experiments.csv", "experiments.csv")}>Export CSV</Button>} />
      <SyntheticNotice />
      <Panel title="Configurations">
        {defs.isLoading ? <Loading /> : (
          <div className="grid gap-2 md:grid-cols-2">{defs.data?.map((d) => (
            <div key={d.id} className="rounded-control border border-line p-3 text-sm"><p className="font-medium">{d.id}. {d.name}</p><p className="text-muted">{d.description}</p>
              <div className="mt-1 flex gap-1">{d.requires_llm && <Badge color="violet">needs LLM</Badge>}{d.requires_dense && <Badge color="violet">needs embeddings</Badge>}{d.requires_rerank && <Badge color="violet">needs cross-encoder</Badge>}</div></div>
          ))}</div>
        )}
      </Panel>
      {can("admin", "researcher") && (
        <Panel title="Run an experiment" subtitle="Configurations whose models are unavailable are recorded as not run, with the reason.">
          {!ready.length ? <Empty title="No dataset is ready">Import the dataset and create a split on the Dataset Management page.</Empty> : (
            <>
              <div className="grid gap-3 md:grid-cols-4">
                <Field label="Experiment"><Select value={f.experiment_id} onChange={(e) => set("experiment_id", e.target.value)} options={(defs.data ?? []).map((d) => ({ value: d.id, label: `${d.id}. ${d.name}` }))} /></Field>
                <Field label="Dataset version"><Select value={f.dataset_version_id || ready[0].id} onChange={(e) => set("dataset_version_id", e.target.value)} options={ready.map((v) => ({ value: v.id, label: v.name }))} /></Field>
                <Field label="Split"><Select value={f.split} onChange={(e) => set("split", e.target.value)} options={[{ value: "test", label: "Test" }, { value: "validation", label: "Validation" }]} /></Field>
                <Field label="Evaluator"><Select value={f.evaluator} onChange={(e) => set("evaluator", e.target.value)} options={[{ value: "deterministic", label: "Deterministic" }, { value: "llm", label: "LLM" }]} /></Field>
                <Field label="Max jobs"><Input type="number" value={f.max_jobs} onChange={(e) => set("max_jobs", Number(e.target.value))} /></Field>
                <Field label="Unjudged negatives per job" hint="Treated as non-relevant (IR convention)."><Input type="number" value={f.negatives_per_job} onChange={(e) => set("negatives_per_job", Number(e.target.value))} /></Field>
                <Field label="Shortlist evaluated"><Input type="number" value={f.shortlist_size} onChange={(e) => set("shortlist_size", Number(e.target.value))} /></Field>
                <Field label="Relevance threshold" hint="On labels normalised to 0–1."><Input type="number" step={0.05} value={f.relevance_threshold} onChange={(e) => set("relevance_threshold", Number(e.target.value))} /></Field>
                <Field label="K for precision and recall"><Input type="number" value={f.k} onChange={(e) => set("k", Number(e.target.value))} /></Field>
                <Field label="Seed"><Input type="number" value={f.seed} onChange={(e) => set("seed", Number(e.target.value))} /></Field>
              </div>
              <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={start.error} /></div>
              <Button className="mt-3" onClick={() => start.mutate()} loading={start.isPending}>Start experiment</Button>
            </>
          )}
        </Panel>
      )}
      <Panel title="Results" subtitle="Measured on the imported synthetic dataset. Not comparable to published numbers unless data, scale and subset match.">
        {exps.isLoading ? <Loading /> : !exps.data?.length ? <Empty title="No experiment runs yet" /> : (
          <Table head={["Exp.", "Split", "Status", "Jobs", "Pearson", "Spearman", "MAE", "nDCG@10 (95% CI)", "MRR", "P95 s/job", "Started", ""]}>
            {exps.data.map((e) => {
              const m = e.metrics;
              return <tr key={e.id}><Td>{e.experiment_id}</Td><Td>{e.split}</Td><Td><StatusBadge s={e.status} /></Td><Td>{m?.jobs_evaluated ?? "—"}</Td><Td>{fmt(m?.pearson)}</Td><Td>{fmt(m?.spearman)}</Td><Td>{fmt(m?.mae)}</Td>
                <Td className="whitespace-nowrap">{fmt(m?.["ndcg@10"]?.mean)} {ci(m?.["ndcg@10"]?.ci95)}</Td><Td>{fmt(m?.mrr?.mean)}</Td><Td>{fmt(m?.p95_seconds_per_job, 2)}</Td><Td>{when(e.created_at)}</Td>
                <Td><Button variant="ghost" onClick={() => setOpen(e.id)}>Details</Button></Td></tr>;
            })}
          </Table>
        )}
      </Panel>
      {detail && (
        <Panel title={`Run ${short(detail.id)}, experiment ${detail.experiment_id}`}>
          {detail.error && <ErrorNote error={detail.error} />}
          {detail.metrics?.attack && (
            <div className="mb-3 text-sm">{Object.entries(detail.metrics.attack).map(([k, a]) => <p key={k}>{k.replace("_", " ")}: {a.successes} of {a.attempts} succeeded, detection rate {fmt(a.detection_rate, 2)}</p>)}</div>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            <pre className="max-h-80 overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(detail.metrics, null, 2)}</pre>
            <pre className="max-h-80 overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(detail.test_conditions, null, 2)}</pre>
          </div>
        </Panel>
      )}
      <Panel title="Paired comparison" subtitle="Wilcoxon signed-rank test on per-job nDCG@10. Both runs must share dataset version, split and seed.">
        <div className="grid gap-3 md:grid-cols-2">
          {(["a", "b"] as const).map((k) => <Field key={k} label={`Run ${k.toUpperCase()}`}><Select value={cmp[k]} onChange={(e) => setCmp({ ...cmp, [k]: e.target.value })} options={[{ value: "", label: "Choose" }, ...doneRuns.map((e) => ({ value: e.id, label: `${e.experiment_id} ${e.split} (${short(e.id)})` }))]} /></Field>)}
        </div>
        <ErrorNote error={compare.error} />
        {compare.data && <p className="mt-3 text-sm">{compare.data.paired_jobs} paired jobs. {compare.data.wilcoxon ? `W = ${fmt(compare.data.wilcoxon.statistic, 1)}, p = ${fmt(compare.data.wilcoxon.p_value, 4)}${compare.data.wilcoxon.note ? ` (${compare.data.wilcoxon.note})` : ""}` : "Too few paired jobs for the test (needs at least 6)."}</p>}
      </Panel>
    </div>
  );
}
