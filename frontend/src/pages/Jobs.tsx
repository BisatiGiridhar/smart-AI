import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CorpusPicker } from "../components/CorpusPicker";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, Table, Td, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { when } from "../lib/format";
import type { Criterion, Rubric } from "../lib/types";

type JobRow = { id: string; title: string; source_kind: string; status: string; split: string | null; created_at: string; approved_rubric_version: number | null };
type JobDetail = JobRow & { text: string; analysis: Record<string, unknown> | null; rubrics: Rubric[] };

export default function Jobs() {
  const { jobId } = useParams();
  return jobId ? <JobView id={jobId} /> : <JobList />;
}

function JobList() {
  const { can } = useAuth();
  const [corpus, setCorpus] = useState("genuine");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const list = useQuery({ queryKey: ["jobs", corpus, q, status, page], queryFn: () => api<{ total: number; items: JobRow[] }>(`/api/jobs?corpus=${encodeURIComponent(corpus)}&q=${encodeURIComponent(q)}&status=${status}&page=${page}&size=25`) });
  return (
    <div className="space-y-6">
      <PageHeader title="Job Descriptions" description="Create or upload jobs, review extracted requirements and approve versioned scoring rubrics." />
      {can("admin", "recruiter") && <CreateJob />}
      <Panel title="Jobs" actions={<span className="text-sm text-muted">{list.data?.total ?? 0} total</span>}>
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <CorpusPicker value={corpus} onChange={(v) => { setCorpus(v); setPage(1); }} />
          <Field label="Search title or source id"><Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></Field>
          <Field label="Status"><Select value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "active", label: "Active" }, { value: "archived", label: "Archived" }, { value: "all", label: "All" }]} /></Field>
        </div>
        {list.isLoading ? <Loading /> : list.error ? <ErrorNote error={list.error} /> : !list.data?.items.length ? <Empty title="No job descriptions in this corpus" /> : (
          <>
            <Table head={["Title", "Source", "Split", "Approved rubric", "Status", "Created"]}>
              {list.data.items.map((j) => (
                <tr key={j.id}><Td><Link className="text-cyan hover:underline" to={`/app/jobs/${j.id}`}>{j.title}</Link></Td>
                  <Td>{j.source_kind === "genuine" ? "genuine" : <Badge color="violet">synthetic</Badge>}</Td><Td>{j.split ?? "—"}</Td>
                  <Td>{j.approved_rubric_version ? `v${j.approved_rubric_version}` : <Badge color="amber">none</Badge>}</Td><Td><StatusBadge s={j.status} /></Td><Td>{when(j.created_at)}</Td></tr>
              ))}
            </Table>
            <Pager page={page} total={list.data.total} size={25} onPage={setPage} />
          </>
        )}
      </Panel>
    </div>
  );
}

export function Pager({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="mt-3 flex items-center gap-2 text-sm">
      <Button variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <span className="text-muted">Page {page} of {pages}</span>
      <Button variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
    </div>
  );
}

function CreateJob() {
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const create = useMutation({
    mutationFn: () => {
      if (file) { const fd = new FormData(); fd.append("title", title); fd.append("file", file); return api<{ id: string }>("/api/jobs/upload", { method: "POST", body: fd }); }
      return api<{ id: string }>("/api/jobs", { method: "POST", json: { title, text } });
    },
    onSuccess: (j) => nav(`/app/jobs/${j.id}`),
  });
  return (
    <Panel title="Add a job description" subtitle="Paste the text or upload a PDF, DOCX or TXT file.">
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-3">
          <Field label="Job title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Document (optional)"><input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" /></Field>
        </div>
        <Field label="Description text" hint="Headings such as Requirements and Preferred help the analyzer separate required from preferred skills.">
          <Textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} disabled={!!file} />
        </Field>
      </div>
      <ErrorNote error={create.error} />
      <Button className="mt-3" onClick={() => create.mutate()} loading={create.isPending} disabled={!title || (!file && text.length < 20)}>Save job</Button>
    </Panel>
  );
}

function JobView({ id }: { id: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["job", id], queryFn: () => api<JobDetail>(`/api/jobs/${id}`) });
  const [draft, setDraft] = useState<Criterion[] | null>(null);
  const [notes, setNotes] = useState("");
  const [origin, setOrigin] = useState<"recruiter" | "auto_draft">("recruiter");
  const analyze = useMutation({ mutationFn: () => api<{ draft_criteria: Criterion[] }>(`/api/jobs/${id}/analyze`, { method: "POST" }),
    onSuccess: (r) => { setDraft(r.draft_criteria); setOrigin("auto_draft"); qc.invalidateQueries({ queryKey: ["job", id] }); } });
  const save = useMutation({ mutationFn: () => api(`/api/jobs/${id}/rubrics`, { method: "POST", json: { criteria: draft, notes, origin } }),
    onSuccess: () => { setDraft(null); qc.invalidateQueries({ queryKey: ["job", id] }); } });
  const approve = useMutation({ mutationFn: (rid: string) => api(`/api/rubrics/${rid}/approve`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["job", id] }) });
  const archive = useMutation({ mutationFn: () => api(`/api/jobs/${id}/archive`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["job", id] }) });
  useEffect(() => setDraft(null), [id]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const j = q.data!;
  const editor = can("admin", "recruiter");
  const a = (j.analysis ?? {}) as { required_skills?: { skill: string; quote: string }[]; preferred_skills?: { skill: string; quote: string }[]; unclassified_skills?: { skill: string }[]; experience_requirement?: { min_years: number; quote: string } | null; responsibilities?: string[]; notes?: string[] };
  return (
    <div className="space-y-6">
      <PageHeader title={j.title} description={<><Link to="/app/jobs" className="text-cyan">All jobs</Link>. {j.source_kind === "genuine" ? "Genuine job" : "Synthetic research job (read-only)"}</>}
        actions={editor && j.source_kind === "genuine" && <Button variant="ghost" onClick={() => archive.mutate()}>{j.status === "active" ? "Archive" : "Restore"}</Button>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Description"><pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap font-sans text-sm">{j.text}</pre></Panel>
        <Panel title="Extracted requirements" subtitle="Deterministic analyzer. Review before building a rubric." actions={editor && <Button variant="ghost" onClick={() => analyze.mutate()} loading={analyze.isPending}>Re-analyze and draft rubric</Button>}>
          {!j.analysis ? <p className="text-sm text-muted">Not analyzed yet.</p> : (
            <div className="space-y-3 text-sm">
              <p><span className="font-medium">Required:</span> {a.required_skills?.map((s) => s.skill).join(", ") || "none found"}</p>
              <p><span className="font-medium">Preferred:</span> {a.preferred_skills?.map((s) => s.skill).join(", ") || "none found"}</p>
              {!!a.unclassified_skills?.length && <p><span className="font-medium">Priority unclear:</span> {a.unclassified_skills.map((s) => s.skill).join(", ")}</p>}
              <p><span className="font-medium">Experience:</span> {a.experience_requirement ? `${a.experience_requirement.min_years} years (“${a.experience_requirement.quote}”)` : "not stated"}</p>
              {!!a.responsibilities?.length && <div><p className="font-medium">Responsibilities</p><ul className="list-disc pl-5 text-muted">{a.responsibilities.slice(0, 8).map((r) => <li key={r}>{r}</li>)}</ul></div>}
              {a.notes?.map((n) => <p key={n} className="text-amber">{n}</p>)}
            </div>
          )}
          <ErrorNote error={analyze.error} />
        </Panel>
      </div>
      {draft && (
        <Panel title="New rubric version" subtitle="Saving creates a draft. A recruiter must approve it before it is used for screening.">
          <RubricEditor criteria={draft} onChange={setDraft} />
          <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
          <ErrorNote error={save.error} />
          <div className="mt-3 flex gap-2"><Button onClick={() => save.mutate()} loading={save.isPending} disabled={!draft.length}>Save draft version</Button><Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button></div>
        </Panel>
      )}
      <Panel title="Rubric versions" actions={editor && !draft && <Button variant="ghost" onClick={() => { setDraft(j.rubrics[0]?.criteria ?? []); setOrigin("recruiter"); }}>{j.rubrics.length ? "Edit as new version" : "Start an empty rubric"}</Button>}>
        {!j.rubrics.length ? <p className="text-sm text-muted">No rubric yet. Analyze the job to draft one.</p> : (
          <div className="space-y-3">
            {j.rubrics.map((r) => (
              <details key={r.id} className="rounded-control border border-line p-3" open={r.status !== "superseded" && r === j.rubrics[0]}>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">Version {r.version}</span><StatusBadge s={r.status} /><Badge>{r.origin === "auto_draft" ? "auto-drafted" : "recruiter"}</Badge>
                  <span className="text-muted">{r.approved_at ? `approved ${when(r.approved_at)}` : `created ${when(r.created_at)}`}</span>
                  {r.status === "draft" && can("admin", "recruiter") && <Button className="ml-auto" onClick={(e) => { e.preventDefault(); approve.mutate(r.id); }} loading={approve.isPending}>Approve</Button>}
                </summary>
                <Table head={["Criterion", "Kind", "Weight", "Max", "Required", "Terms"]}>
                  {r.criteria.map((c) => <tr key={c.id}><Td>{c.label}</Td><Td>{c.kind}</Td><Td>{c.weight}</Td><Td>{c.max_rating}</Td><Td>{c.required ? "yes" : "no"}</Td><Td className="text-muted">{c.kind === "experience_years" ? `${c.min_years} years` : c.terms.join(", ")}</Td></tr>)}
                </Table>
              </details>
            ))}
          </div>
        )}
        <ErrorNote error={approve.error} />
      </Panel>
    </div>
  );
}

function RubricEditor({ criteria, onChange }: { criteria: Criterion[]; onChange: (c: Criterion[]) => void }) {
  const set = (i: number, patch: Partial<Criterion>) => onChange(criteria.map((c, k) => (k === i ? { ...c, ...patch } : c)));
  const add = () => onChange([...criteria, { id: `skill:new-${criteria.length + 1}`, label: "", kind: "skill", weight: 1, max_rating: 4, terms: [], required: false }]);
  return (
    <div className="mb-3 overflow-x-auto">
      <table className="w-full min-w-[820px] text-sm">
        <thead><tr className="text-left text-muted"><th className="p-1">Label</th><th className="p-1">Kind</th><th className="p-1">Weight</th><th className="p-1">Max rating</th><th className="p-1">Required</th><th className="p-1">Terms or minimum years</th><th /></tr></thead>
        <tbody>
          {criteria.map((c, i) => (
            <tr key={i}>
              <td className="p-1"><Input value={c.label} onChange={(e) => set(i, { label: e.target.value, id: c.id.startsWith("skill:new") ? `skill:${e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : c.id })} /></td>
              <td className="p-1"><Select value={c.kind} onChange={(e) => set(i, { kind: e.target.value as Criterion["kind"] })} options={[{ value: "skill", label: "Skill" }, { value: "experience_years", label: "Years of experience" }, { value: "free_text", label: "Reviewer judgement" }]} /></td>
              <td className="p-1"><Input type="number" min={0} step={0.5} value={c.weight} onChange={(e) => set(i, { weight: Number(e.target.value) })} className="w-20" /></td>
              <td className="p-1"><Input type="number" min={1} value={c.max_rating} onChange={(e) => set(i, { max_rating: Number(e.target.value) })} className="w-20" /></td>
              <td className="p-1 text-center"><input type="checkbox" checked={c.required} onChange={(e) => set(i, { required: e.target.checked })} aria-label="Required" /></td>
              <td className="p-1">{c.kind === "experience_years" ? <Input type="number" min={0} value={c.min_years ?? ""} onChange={(e) => set(i, { min_years: Number(e.target.value) })} className="w-24" /> :
                <Input value={c.terms.join(", ")} onChange={(e) => set(i, { terms: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })} />}</td>
              <td className="p-1"><Button variant="quiet" onClick={() => onChange(criteria.filter((_, k) => k !== i))}>Remove</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button variant="ghost" className="mt-2" onClick={add}>Add criterion</Button>
    </div>
  );
}
