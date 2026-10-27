import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Empty, ErrorNote, Field, PageHeader, Panel, Select, StatusBadge, TaskBar } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ci, fmt, short, when } from "../lib/format";
import { useTask } from "../lib/hooks";

type Bin = { lower: number; upper: number; count: number; confidence: number | null; accuracy: number | null };
type Cal = { id: string; validation_run_id: string; test_run_id: string; status: string; error: string | null; params: Record<string, number> | null; metrics: Record<string, unknown> | null; bins: { raw: Bin[]; calibrated: Bin[] } | null; created_at: string };
type Exp = { id: string; experiment_id: string; split: string; status: string; created_at: string };

export default function Calibration() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const cals = useQuery({ queryKey: ["cals"], queryFn: () => api<Cal[]>("/api/calibration/runs") });
  const exps = useQuery({ queryKey: ["exps"], queryFn: () => api<Exp[]>("/api/experiments/runs") });
  const [val, setVal] = useState("");
  const [test, setTest] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId);
  const start = useMutation({ mutationFn: () => api<{ task_id: string }>("/api/calibration/runs", { method: "POST", json: { validation_run_id: val, test_run_id: test } }),
    onSuccess: (r) => { setTaskId(r.task_id); qc.invalidateQueries({ queryKey: ["cals"] }); } });
  const done = (exps.data ?? []).filter((e) => e.status === "completed");
  const opt = (split: string) => [{ value: "", label: "Choose" }, ...done.filter((e) => e.split === split).map((e) => ({ value: e.id, label: `Experiment ${e.experiment_id} (${when(e.created_at)})` }))];
  const latest = cals.data?.find((c) => c.status === "completed");
  return (
    <div className="space-y-6">
      <PageHeader title="Confidence and Calibration" description="Scores become probability estimates only after calibration against labelled outcomes on a validation split, checked on a separate test split." />
      <p className="text-sm text-muted">An LLM's self-reported confidence is never treated as a probability. The rubric score S is a weighted evidence score; without calibration it is not a probability.</p>
      {can("admin", "researcher") && (
        <Panel title="Calibrate" subtitle="Run the same experiment twice, once on the validation split and once on the test split, then pair them here.">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Validation run (fitting)"><Select value={val} onChange={(e) => setVal(e.target.value)} options={opt("validation")} /></Field>
            <Field label="Test run (evaluation)"><Select value={test} onChange={(e) => setTest(e.target.value)} options={opt("test")} /></Field>
          </div>
          <div className="mt-3 space-y-2"><TaskBar task={task.data} /><ErrorNote error={start.error} /></div>
          <Button className="mt-3" onClick={() => start.mutate()} loading={start.isPending} disabled={!val || !test}>Fit and evaluate</Button>
        </Panel>
      )}
      {!latest ? (
        <Empty title="Calibration not yet validated">No completed calibration exists for this workspace. Until one does, review routing relies on evidence coverage and flags, not on probabilities.</Empty>
      ) : (
        <Panel title={`Latest calibration ${short(latest.id)}`} subtitle={String(latest.metrics?.note ?? "")}>
          <div className="mb-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <p>Test pairs: <b>{String(latest.metrics?.test_n)}</b></p>
            <p>ECE raw S: <b>{fmt(latest.metrics?.ece_raw as number)}</b></p>
            <p>ECE calibrated: <b>{fmt(latest.metrics?.ece_calibrated as number)}</b> {ci(latest.metrics?.ece_calibrated_ci95 as number[])}</p>
            <p>Brier calibrated: <b>{fmt(latest.metrics?.brier_calibrated as number)}</b> {ci(latest.metrics?.brier_calibrated_ci95 as number[])}</p>
            <p>Brier raw S: <b>{fmt(latest.metrics?.brier_raw as number)}</b></p>
            <p>Platt a, b: <b>{fmt(latest.params?.a)}, {fmt(latest.params?.b)}</b></p>
            <p>Skipped (no score): <b>{String(latest.metrics?.test_skipped_no_score)}</b></p>
          </div>
          <p className="mb-2 text-sm font-medium">Reliability diagram (test split)</p>
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" />
                <XAxis type="number" dataKey="confidence" domain={[0, 1]} stroke="rgb(var(--muted))" fontSize={12} name="Predicted" />
                <YAxis type="number" dataKey="accuracy" domain={[0, 1]} stroke="rgb(var(--muted))" fontSize={12} name="Observed" />
                <Tooltip contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--line))" }} />
                <Legend />
                <Line data={[{ confidence: 0, accuracy: 0 }, { confidence: 1, accuracy: 1 }]} dataKey="accuracy" name="Perfect calibration" stroke="rgb(var(--muted))" strokeDasharray="4 4" dot={false} />
                <Line data={(latest.bins?.raw ?? []).filter((b) => b.count)} dataKey="accuracy" name="Raw S" stroke="rgb(var(--violet))" />
                <Line data={(latest.bins?.calibrated ?? []).filter((b) => b.count)} dataKey="accuracy" name="Calibrated" stroke="rgb(var(--cyan))" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}
      {!!cals.data?.length && (
        <Panel title="All calibration runs">
          <ul className="space-y-1 text-sm">{cals.data.map((c) => <li key={c.id}><span className="font-mono text-xs">{short(c.id)}</span> <StatusBadge s={c.status} /> {when(c.created_at)} {c.error && <span className="text-danger">{c.error}</span>}</li>)}</ul>
        </Panel>
      )}
    </div>
  );
}
