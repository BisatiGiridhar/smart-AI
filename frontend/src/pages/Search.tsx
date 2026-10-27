import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CorpusPicker } from "../components/CorpusPicker";
import { Button, Empty, ErrorNote, Field, Input, PageHeader, Panel, Select, StatusBadge, Table, TaskBar, Td } from "../components/ui";
import { api } from "../lib/api";
import { fmt } from "../lib/format";
import { useTask } from "../lib/hooks";

type Result = { resume_id: string; display_ref: string; final_position: number; bm25_rank: number | null; bm25_score: number | null; dense_rank: number | null; dense_similarity: number | null; rrf_rank: number | null; rrf_score: number | null; cross_encoder_score: number | null; snippet: string };
type SearchRes = { query: string; criteria_source: string; results: Result[]; trace: { agent: string; status: string; detail: string; duration_ms: number }[]; providers: Record<string, unknown>; pool_size: number; score_note: string; message?: string };

export function JobPicker({ corpus, value, onChange }: { corpus: string; value: string; onChange: (v: string) => void }) {
  const jobs = useQuery({ queryKey: ["jobs-pick", corpus], queryFn: () => api<{ items: { id: string; title: string }[] }>(`/api/jobs?corpus=${encodeURIComponent(corpus)}&size=200`) });
  return <Field label="Job"><Select value={value} onChange={(e) => onChange(e.target.value)} options={[{ value: "", label: jobs.isLoading ? "Loading" : "Choose a job" }, ...(jobs.data?.items ?? []).map((j) => ({ value: j.id, label: j.title }))]} /></Field>;
}

export default function Search() {
  const [corpus, setCorpus] = useState("genuine");
  const [jobId, setJobId] = useState("");
  const [k, setK] = useState(60);
  const [size, setSize] = useState(25);
  const [dense, setDense] = useState(true);
  const [rerank, setRerank] = useState(true);
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId);
  const idx = useQuery({ queryKey: ["index", corpus, task.data?.status], queryFn: () => api<Record<string, unknown>>(`/api/index/status?corpus=${encodeURIComponent(corpus)}`) });
  const run = useMutation({ mutationFn: () => api<SearchRes>("/api/search", { method: "POST", json: { job_id: jobId, corpus, rrf_k: k, shortlist_size: size, use_dense: dense, use_rerank: rerank } }) });
  const build = useMutation({ mutationFn: () => api<{ task_id: string }>("/api/index/build", { method: "POST", json: { corpus } }), onSuccess: (r) => setTaskId(r.task_id) });
  const r = run.data;
  return (
    <div className="space-y-6">
      <PageHeader title="Hybrid Candidate Search" description="BM25 and dense retrieval fused with Reciprocal Rank Fusion, then reranked by a cross-encoder. Every stage's rank is shown." />
      <Panel title="Search settings">
        <div className="grid gap-3 md:grid-cols-3">
          <CorpusPicker value={corpus} onChange={(v) => { setCorpus(v); setJobId(""); }} />
          <JobPicker corpus={corpus} value={jobId} onChange={setJobId} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="RRF k" hint="RRF(d) = Σ 1 / (k + rank)"><Input type="number" min={0} value={k} onChange={(e) => setK(Number(e.target.value))} /></Field>
            <Field label="Shortlist size"><Input type="number" min={1} max={200} value={size} onChange={(e) => setSize(Number(e.target.value))} /></Field>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={dense} onChange={(e) => setDense(e.target.checked)} />Dense retrieval</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} />Cross-encoder rerank</label>
          <span className="text-muted">Vector index: {String(idx.data?.index_count ?? 0)} embedded with {String(idx.data?.embedding_model ?? "?")}</span>
          <Button variant="ghost" onClick={() => build.mutate()} loading={build.isPending}>Build or update vector index</Button>
        </div>
        <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={build.error} /><ErrorNote error={run.error} /></div>
        <Button className="mt-3" onClick={() => run.mutate()} loading={run.isPending} disabled={!jobId}>Run search</Button>
      </Panel>
      {r && (
        <>
          <Panel title="Stages" subtitle={`Query built from ${r.criteria_source}. Pool of ${r.pool_size} resumes.`}>
            <div className="flex flex-wrap gap-2">{r.trace.map((t) => <div key={t.agent} className="rounded-control border border-line px-3 py-2 text-sm"><div className="flex items-center gap-2">{t.agent.replace(/_/g, " ")} <StatusBadge s={t.status} /></div><div className="text-xs text-muted">{t.detail || "—"} ({t.duration_ms} ms)</div></div>)}</div>
            <p className="mt-3 font-mono text-xs text-muted">{r.query}</p>
          </Panel>
          <Panel title="Shortlist" subtitle={r.score_note}>
            {!r.results.length ? <Empty title="No resumes matched">{r.message ?? "No resume contained the query terms. Try another job or build the vector index for semantic matches."}</Empty> : (
              <Table head={["#", "Resume", "BM25 rank", "BM25", "Dense rank", "Cosine", "RRF rank", "RRF", "Cross-encoder", "Snippet"]}>
                {r.results.map((x) => (
                  <tr key={x.resume_id}><Td>{x.final_position}</Td><Td>{x.display_ref}</Td><Td>{x.bm25_rank ?? "—"}</Td><Td>{fmt(x.bm25_score, 2)}</Td><Td>{x.dense_rank ?? "—"}</Td><Td>{fmt(x.dense_similarity)}</Td>
                    <Td>{x.rrf_rank ?? "—"}</Td><Td>{fmt(x.rrf_score, 4)}</Td><Td>{fmt(x.cross_encoder_score)}</Td><Td className="max-w-xs truncate text-muted">{x.snippet}</Td></tr>
                ))}
              </Table>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
