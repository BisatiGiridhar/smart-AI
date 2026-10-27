import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Empty, ErrorNote, Loading, PageHeader, Panel, Table, Td } from "../components/ui";
import { api, download } from "../lib/api";
import { ci, fmt } from "../lib/format";

type A = { evaluation_runs: number; criterion_status_counts: Record<string, number>; coverage_histogram: { bucket: string; count: number }[]; review_status_counts: Record<string, number>;
  experiments: { experiment_id: string; split: string; run_id: string; metrics: Record<string, any> | null }[]; latest_calibration: { metrics: Record<string, number> } | null }; // eslint-disable-line @typescript-eslint/no-explicit-any

const tip = { background: "rgb(var(--surface))", border: "1px solid rgb(var(--line))" };

export default function Analytics() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: () => api<A>("/api/analytics") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const d = q.data!;
  const statuses = Object.entries(d.criterion_status_counts).map(([status, count]) => ({ status: status.replace("_", " "), count }));
  const ndcg = d.experiments.filter((e) => e.metrics?.["ndcg@10"]?.mean != null).map((e) => ({ name: `${e.experiment_id} (${e.split})`, value: e.metrics!["ndcg@10"].mean }));
  return (
    <div className="space-y-6">
      <PageHeader title="Analytics and Reports" description="Aggregates computed from stored evaluation results and experiment runs." actions={<Button variant="ghost" onClick={() => download("/api/reports/experiments.csv", "experiments.csv")}>Download experiment report (CSV)</Button>} />
      {d.evaluation_runs === 0 && !d.experiments.length ? <Empty title="No data available yet">Run an evaluation or an experiment to populate these reports.</Empty> : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Criterion outcomes across completed runs">
              {!statuses.length ? <p className="text-sm text-muted">No evaluated criteria.</p> : <div className="h-64"><ResponsiveContainer><BarChart data={statuses}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" /><XAxis dataKey="status" fontSize={12} stroke="rgb(var(--muted))" /><YAxis fontSize={12} stroke="rgb(var(--muted))" allowDecimals={false} /><Tooltip contentStyle={tip} /><Bar dataKey="count" fill="rgb(var(--cyan))" /></BarChart></ResponsiveContainer></div>}
            </Panel>
            <Panel title="Evidence coverage distribution">
              <div className="h-64"><ResponsiveContainer><BarChart data={d.coverage_histogram}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" /><XAxis dataKey="bucket" fontSize={11} stroke="rgb(var(--muted))" /><YAxis fontSize={12} stroke="rgb(var(--muted))" allowDecimals={false} /><Tooltip contentStyle={tip} /><Bar dataKey="count" fill="rgb(var(--violet))" /></BarChart></ResponsiveContainer></div>
            </Panel>
          </div>
          <Panel title="Latest result per experiment" subtitle="Synthetic research dataset. Copy these into Tables IV and V of the paper only with their test conditions.">
            {!d.experiments.length ? <p className="text-sm text-muted">No completed experiments.</p> : (
              <>
                {ndcg.length > 0 && <div className="mb-4 h-56"><ResponsiveContainer><BarChart data={ndcg}><CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" /><XAxis dataKey="name" fontSize={12} stroke="rgb(var(--muted))" /><YAxis domain={[0, 1]} fontSize={12} stroke="rgb(var(--muted))" /><Tooltip contentStyle={tip} /><Bar dataKey="value" name="nDCG@10" fill="rgb(var(--cyan))" /></BarChart></ResponsiveContainer></div>}
                <Table head={["Exp.", "Split", "Pearson", "Spearman", "MAE", "RMSE", "nDCG@10", "95% CI", "MRR", "P95 s/job", "Cost/resume"]}>
                  {d.experiments.map((e) => { const m = e.metrics ?? {}; return (
                    <tr key={e.run_id}><Td>{e.experiment_id}</Td><Td>{e.split}</Td><Td>{fmt(m.pearson)}</Td><Td>{fmt(m.spearman)}</Td><Td>{fmt(m.mae)}</Td><Td>{fmt(m.rmse)}</Td><Td>{fmt(m["ndcg@10"]?.mean)}</Td><Td>{ci(m["ndcg@10"]?.ci95)}</Td><Td>{fmt(m.mrr?.mean)}</Td><Td>{fmt(m.p95_seconds_per_job, 2)}</Td><Td>{m.cost_per_resume_usd == null ? "n/a" : `$${fmt(m.cost_per_resume_usd, 4)}`}</Td></tr>); })}
                </Table>
              </>
            )}
          </Panel>
          <Panel title="Review status">
            <p className="text-sm">{Object.entries(d.review_status_counts).map(([k, v]) => `${k.replace("_", " ")}: ${v}`).join(". ") || "No results."}</p>
            {d.latest_calibration && <p className="mt-2 text-sm">Latest calibrated ECE {fmt(d.latest_calibration.metrics.ece_calibrated)}, Brier {fmt(d.latest_calibration.metrics.brier_calibrated)}.</p>}
          </Panel>
        </>
      )}
    </div>
  );
}
