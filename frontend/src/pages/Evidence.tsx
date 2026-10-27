import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Button, DecisionNotice, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmt, pct, when } from "../lib/format";
import type { AssessmentT, Evidence as Ev } from "../lib/types";

type Detail = { id: string; final_rank: number; score: number | null; coverage: number | null; s_low: number | null; s_high: number | null; review_status: string; run_id: string;
  score_detail: { per_criterion: { criterion_id: string; label: string; status: string; rating: number | null; max_rating: number; normalized: number | null; weight: number; normalized_weight: number }[]; review_reasons: string[]; insufficient_evidence: boolean };
  assessments: AssessmentT[]; feedback: { technical: string[]; experience: string[]; recruiter: string[]; note: string }; skill_gaps: { label: string; type: string; detail: string; suggested_next_step: string; required: boolean }[];
  injection_flags: { pattern: string; start: number; end: number }[]; resume: { display_ref: string; source_kind: string; text: string };
  reviews: { id: string; decision: string; override_score: number | null; comment: string; created_at: string }[] };

export default function Evidence() {
  const { resultId } = useParams();
  return resultId ? <CandidateEvidence id={resultId} /> : <ReviewQueue />;
}

function ReviewQueue() {
  const q = useQuery({ queryKey: ["pending"], queryFn: () => api<{ id: string; run_id: string; display_ref: string; final_rank: number; score: number | null; coverage: number | null; reasons: string[] }[]>("/api/reviews/pending") });
  return (
    <div className="space-y-6">
      <PageHeader title="Evidence Explorer" description="Open a ranked candidate to see each criterion's status, the quoted evidence in the source text, and the reviewer record." />
      <Panel title="Human review queue" subtitle="Candidates with contradicted, unsupported or low-coverage evidence, or instruction-like text.">
        {q.isLoading ? <Loading /> : q.error ? <ErrorNote error={q.error} /> : !q.data?.length ? <Empty title="Nothing is waiting for review">Results flagged during evaluation runs appear here. Open a run on the Candidate Ranking page to explore any candidate.</Empty> : (
          <Table head={["Candidate", "Rank", "S", "Coverage", "Why it needs review"]}>
            {q.data.map((r) => <tr key={r.id}><Td><Link className="text-cyan hover:underline" to={`/app/evidence/${r.id}`}>{r.display_ref}</Link></Td><Td>{r.final_rank}</Td><Td>{fmt(r.score)}</Td><Td>{pct(r.coverage)}</Td><Td className="text-muted">{r.reasons.join("; ")}</Td></tr>)}
          </Table>
        )}
      </Panel>
    </div>
  );
}

function CandidateEvidence({ id }: { id: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["cand", id], queryFn: () => api<Detail>(`/api/candidate-results/${id}`) });
  const [active, setActive] = useState<Ev | null>(null);
  const [decision, setDecision] = useState("agree");
  const [override, setOverride] = useState("");
  const [comment, setComment] = useState("");
  const review = useMutation({ mutationFn: () => api(`/api/candidate-results/${id}/review`, { method: "POST", json: { decision, comment, override_score: decision === "override" ? Number(override) : null } }),
    onSuccess: () => { setComment(""); qc.invalidateQueries({ queryKey: ["cand", id] }); qc.invalidateQueries({ queryKey: ["pending"] }); } });
  const segments = useMemo(() => {
    if (!q.data) return [];
    const text = q.data.resume.text;
    const marks: { start: number; end: number; kind: "ev" | "inj" }[] = [];
    q.data.assessments.forEach((a) => a.evidence.forEach((e) => marks.push({ start: e.start, end: e.end, kind: "ev" })));
    q.data.injection_flags.forEach((f) => marks.push({ start: f.start, end: f.end, kind: "inj" }));
    marks.sort((a, b) => a.start - b.start);
    const out: { text: string; kind?: "ev" | "inj"; start: number }[] = [];
    let pos = 0;
    for (const m of marks) {
      if (m.start < pos) continue;
      out.push({ text: text.slice(pos, m.start), start: pos });
      out.push({ text: text.slice(m.start, m.end), kind: m.kind, start: m.start });
      pos = m.end;
    }
    out.push({ text: text.slice(pos), start: pos });
    return out;
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const d = q.data!;
  const byId = Object.fromEntries(d.assessments.map((a) => [a.criterion_id, a]));
  return (
    <div className="space-y-6">
      <PageHeader title={`${d.resume.display_ref}, rank ${d.final_rank}`} description={<><Link className="text-cyan" to={`/app/ranking/${d.run_id}`}>Back to ranking</Link>. {d.resume.source_kind === "genuine" ? "Genuine candidate." : "Synthetic research record."}</>} />
      <DecisionNotice />
      <div className="grid gap-3 sm:grid-cols-4">
        <Box label="Normalized verified score S" value={d.score_detail.insufficient_evidence ? "Insufficient evidence" : fmt(d.score)} />
        <Box label="Evidence coverage C" value={pct(d.coverage)} />
        <Box label="Weighted bounds" value={`${fmt(d.s_low, 2)} to ${fmt(d.s_high, 2)}`} />
        <Box label="Review" value={<StatusBadge s={d.review_status} />} />
      </div>
      <p className="text-sm text-muted">S averages only verified criteria. The bounds show the weighted total if every unverified criterion scored zero (lower) or full marks (upper).</p>
      <div className="grid gap-6 lg:grid-cols-[1.05fr_1fr]">
        <Panel title="Criteria" subtitle="Not found means the resume does not mention it. It is not proof the candidate lacks the skill.">
          <div className="space-y-3">
            {d.score_detail.per_criterion.map((p) => {
              const a = byId[p.criterion_id];
              return (
                <div key={p.criterion_id} className="rounded-control border border-line p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{p.label}</span><StatusBadge s={p.status} /><span className="text-muted">weight {p.weight}, rating {p.rating ?? "—"}/{p.max_rating}</span>{a?.method === "llm" && <Badge color="violet">LLM judgement</Badge>}</div>
                  <p className="mt-1 text-muted">{a?.explanation}</p>
                  {a?.evidence.map((e, i) => (
                    <button key={i} onClick={() => { setActive(e); document.getElementById(`seg-${e.start}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); }}
                      className="mt-2 block w-full rounded-control border border-line bg-raised p-2 text-left font-mono text-xs hover:border-cyan">
                      “{e.quote}” <span className="text-muted">[{e.start}–{e.end}{e.page ? `, page ${e.page}` : ""}, {e.verification}]</span>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel title="Source text" subtitle="Highlighted spans are verified evidence. Dashed amber spans are instruction-like text treated as data.">
          <pre className="max-h-[44rem] overflow-auto whitespace-pre-wrap font-mono text-[13px] leading-relaxed">
            {segments.map((s, i) => s.kind === "ev" ? <mark id={`seg-${s.start}`} key={i} className={`evidence-mark text-ink ${active?.start === s.start ? "evidence-mark-active" : ""}`}>{s.text}</mark>
              : s.kind === "inj" ? <mark key={i} className="injection-mark text-ink">{s.text}</mark> : <span key={i}>{s.text}</span>)}
          </pre>
        </Panel>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Feedback perspectives" subtitle={d.feedback.note}>
          {(["technical", "experience", "recruiter"] as const).map((k) => (
            <div key={k} className="mb-3 text-sm"><p className="font-medium capitalize">{k}</p><ul className="list-disc pl-5 text-muted">{(d.feedback[k] ?? []).map((t) => <li key={t}>{t}</li>)}</ul></div>
          ))}
        </Panel>
        <Panel title="Skill gaps and next steps">
          {!d.skill_gaps.length ? <p className="text-sm text-muted">No gaps: every criterion has verified evidence.</p> : (
            <ul className="space-y-2 text-sm">{d.skill_gaps.map((g) => <li key={g.label}><span className="font-medium">{g.label}</span> {g.required && <Badge color="amber">required</Badge>} <span className="text-muted">{g.detail} {g.suggested_next_step}</span></li>)}</ul>
          )}
        </Panel>
      </div>
      <Panel title="Reviewer decision" subtitle="Your decision and comment are stored with the result and in the audit log.">
        {d.reviews.map((r) => <p key={r.id} className="mb-1 text-sm"><StatusBadge s={r.decision} /> {r.override_score !== null && `override ${r.override_score}`} <span className="text-muted">{r.comment} ({when(r.created_at)})</span></p>)}
        {can("admin", "recruiter", "reviewer") && (
          <div className="mt-3 grid gap-3 md:grid-cols-[12rem_10rem_1fr]">
            <Field label="Decision"><Select value={decision} onChange={(e) => setDecision(e.target.value)} options={[{ value: "agree", label: "Agree with assessment" }, { value: "override", label: "Override score" }, { value: "needs_information", label: "Needs more information" }]} /></Field>
            {decision === "override" ? <Field label="Score (0 to 1)"><Input type="number" min={0} max={1} step={0.05} value={override} onChange={(e) => setOverride(e.target.value)} /></Field> : <div />}
            <Field label="Comment"><Textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          </div>
        )}
        <ErrorNote error={review.error} />
        {can("admin", "recruiter", "reviewer") && <Button className="mt-3" onClick={() => review.mutate()} loading={review.isPending} disabled={comment.length < 3}>Record decision</Button>}
      </Panel>
    </div>
  );
}

const Box = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="rounded-panel border border-line bg-surface px-4 py-3"><div className="text-sm text-muted">{label}</div><div className="mt-1 text-lg font-semibold tabular-nums">{value}</div></div>
);
