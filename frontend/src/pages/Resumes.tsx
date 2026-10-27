import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CorpusPicker } from "../components/CorpusPicker";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, Table, Td } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { when } from "../lib/format";
import { Pager } from "./Jobs";

type Row = { id: string; display_ref: string; source_kind: string; original_filename: string | null; extraction_method: string; split: string | null; created_at: string; skills: string[]; missing_fields: string[]; injection_flagged: boolean; consent_recorded: boolean };
type Item = { value: string; start: number; end: number; page?: number | null };
type Detail = Row & { text: string; extraction: Record<string, unknown> | null; extraction_warnings: string[]; corrections: Record<string, unknown>[]; injection_flags: { pattern: string; start: number; end: number }[]; consent: Record<string, string> | null; has_file: boolean };
const FIELDS = ["skills", "education", "experience", "employment_history", "projects", "certifications", "achievements"] as const;

export default function Resumes() {
  const { resumeId } = useParams();
  return resumeId ? <ResumeView id={resumeId} /> : <ResumeList />;
}

function ResumeList() {
  const { can } = useAuth();
  const [corpus, setCorpus] = useState(can("researcher") ? "" : "genuine");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const list = useQuery({ queryKey: ["resumes", corpus, q, page], enabled: !!corpus,
    queryFn: () => api<{ total: number; items: Row[] }>(`/api/resumes?corpus=${encodeURIComponent(corpus)}&q=${encodeURIComponent(q)}&page=${page}&size=25`) });
  return (
    <div className="space-y-6">
      <PageHeader title="Resume Management" description="Upload genuine resumes with consent records, or browse an imported research dataset. Every extracted item links back to its source text." />
      {can("admin", "recruiter") && <Upload />}
      <Panel title="Resumes" actions={<span className="text-sm text-muted">{list.data?.total ?? 0} total</span>}>
        <div className="mb-4 grid gap-3 md:grid-cols-2">
          <CorpusPicker value={corpus} onChange={(v) => { setCorpus(v); setPage(1); }} />
          <Field label="Search reference or text"><Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></Field>
        </div>
        {!corpus ? <p className="text-sm text-muted">Choose a corpus.</p> : list.isLoading ? <Loading /> : list.error ? <ErrorNote error={list.error} /> : !list.data?.items.length ? (
          <Empty title={corpus === "genuine" ? "No genuine resumes yet" : "No resumes in this dataset"}>{corpus === "genuine" ? "Upload resumes above. Each upload needs a lawful basis, consent reference and retention date." : "Import the dataset on the Dataset Management page."}</Empty>
        ) : (
          <>
            <Table head={["Reference", "Skills found", "Missing sections", "Flags", "Split", "Added"]}>
              {list.data.items.map((r) => (
                <tr key={r.id}>
                  <Td><Link className="text-cyan hover:underline" to={`/app/resumes/${r.id}`}>{r.display_ref}</Link></Td>
                  <Td className="max-w-sm text-muted">{r.skills.join(", ") || "none"}</Td>
                  <Td className="text-muted">{r.missing_fields.join(", ") || "none"}</Td>
                  <Td>{r.injection_flagged && <Badge color="amber">instruction-like text</Badge>}</Td>
                  <Td>{r.split ?? "—"}</Td><Td>{when(r.created_at)}</Td>
                </tr>
              ))}
            </Table>
            <Pager page={page} total={list.data.total} size={25} onPage={setPage} />
          </>
        )}
      </Panel>
    </div>
  );
}

function Upload() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<FileList | null>(null);
  const [basis, setBasis] = useState("");
  const [ref, setRef] = useState("");
  const [until, setUntil] = useState("");
  const up = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      Array.from(files ?? []).forEach((f) => fd.append("files", f));
      fd.append("lawful_basis", basis); fd.append("consent_reference", ref); fd.append("retention_until", until);
      return api<{ created: { id: string; display_ref: string; warnings: string[]; injection_flagged: boolean }[]; errors: { file: string; error: string }[] }>("/api/resumes/upload", { method: "POST", body: fd });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["resumes"] }),
  });
  return (
    <Panel title="Upload genuine resumes" subtitle="PDF, DOCX or TXT. Scanned PDFs use OCR when it is installed on the server. Files are stored privately under random names.">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <Field label="Files (up to 50)"><input type="file" multiple accept=".pdf,.docx,.txt" onChange={(e) => setFiles(e.target.files)} className="text-sm" /></Field>
        <Field label="Lawful basis" hint="For example: applicant consent"><Input value={basis} onChange={(e) => setBasis(e.target.value)} /></Field>
        <Field label="Consent or requisition reference"><Input value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
        <Field label="Retain until"><Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></Field>
      </div>
      <ErrorNote error={up.error} />
      <Button className="mt-3" onClick={() => up.mutate()} loading={up.isPending} disabled={!files?.length || basis.length < 3 || !ref || !until}>Upload and extract</Button>
      {up.data && (
        <div className="mt-3 space-y-1 text-sm">
          {up.data.created.map((c) => <p key={c.id} className="text-ok">Added {c.display_ref}{c.injection_flagged ? " (instruction-like text flagged for review)" : ""}{c.warnings.length ? `: ${c.warnings.join(" ")}` : ""}</p>)}
          {up.data.errors.map((e) => <p key={e.file} className="text-danger">{e.file}: {e.error}</p>)}
        </div>
      )}
    </Panel>
  );
}

function ResumeView({ id }: { id: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["resume", id], queryFn: () => api<Detail>(`/api/resumes/${id}`) });
  const [focus, setFocus] = useState<Item | null>(null);
  const [corr, setCorr] = useState({ field: "skills", action: "remove", index: "0", value: "", reason: "" });
  const fix = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { field: corr.field, action: corr.action, reason: corr.reason };
      if (corr.action !== "add") body.index = Number(corr.index);
      if (corr.action !== "remove") {
        const sel = window.getSelection()?.toString() ?? "";
        const start = q.data!.text.indexOf(sel || corr.value);
        body.value = corr.value; body.start = start; body.end = start + (sel || corr.value).length;
      }
      return api(`/api/resumes/${id}/corrections`, { method: "POST", json: body });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["resume", id] }),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const r = q.data!;
  const ex = (r.extraction ?? {}) as Record<string, Item[] | string[] | unknown>;
  const text = r.text;
  const before = focus ? text.slice(0, focus.start) : text;
  const mark = focus ? text.slice(focus.start, focus.end) : "";
  const after = focus ? text.slice(focus.end) : "";
  return (
    <div className="space-y-6">
      <PageHeader title={r.display_ref} description={<><Link to="/app/resumes" className="text-cyan">All resumes</Link>. {r.source_kind === "genuine" ? "Genuine candidate record." : "Synthetic research record — not a genuine candidate."}</>} />
      {r.extraction_warnings.map((w) => <p key={w} className="text-sm text-amber">{w}</p>)}
      {r.injection_flags.length > 0 && <ErrorNote error={`Instruction-like text found (${r.injection_flags.map((f) => f.pattern).join(", ")}). It is treated as data and the record is routed to review.`} />}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Panel title="Extracted fields" subtitle="Select an item to highlight its source passage. Missing fields are reported, never filled in.">
          <div className="space-y-4 text-sm">
            {FIELDS.map((f) => {
              const items = (ex[f] as Item[] | undefined) ?? [];
              return (
                <div key={f}>
                  <p className="font-medium capitalize">{f.replace("_", " ")} <span className="text-muted">({items.length})</span></p>
                  {items.length === 0 ? <p className="text-muted">Not found in the document.</p> : (
                    <ul className="mt-1 flex flex-wrap gap-1.5">
                      {items.slice(0, 40).map((it, i) => (
                        <li key={i}><button onClick={() => setFocus(it)} className={`rounded-control border px-2 py-0.5 text-left text-xs ${focus === it ? "border-cyan text-cyan" : "border-line hover:border-cyan"}`}>
                          {f === "skills" ? it.value : it.value.slice(0, 70)}{it.page ? ` (p.${it.page})` : ""}</button></li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel title="Source text" subtitle={r.extraction_method}>
          <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap font-mono text-[13px] leading-relaxed">{before}{focus && <mark className="evidence-mark text-ink">{mark}</mark>}{after}</pre>
        </Panel>
      </div>
      {can("admin", "recruiter", "reviewer") && (
        <Panel title="Correct an extraction error" subtitle="Corrections are stored with your reason in the audit history. For additions, select the passage in the source text first.">
          <div className="grid gap-3 md:grid-cols-5">
            <Field label="Field"><Select value={corr.field} onChange={(e) => setCorr({ ...corr, field: e.target.value })} options={FIELDS.map((f) => ({ value: f, label: f }))} /></Field>
            <Field label="Action"><Select value={corr.action} onChange={(e) => setCorr({ ...corr, action: e.target.value })} options={[{ value: "remove", label: "Remove item" }, { value: "edit", label: "Edit item" }, { value: "add", label: "Add item" }]} /></Field>
            {corr.action !== "add" && <Field label="Item number (from 0)"><Input type="number" min={0} value={corr.index} onChange={(e) => setCorr({ ...corr, index: e.target.value })} /></Field>}
            {corr.action !== "remove" && <Field label="Value"><Input value={corr.value} onChange={(e) => setCorr({ ...corr, value: e.target.value })} /></Field>}
            <Field label="Reason"><Input value={corr.reason} onChange={(e) => setCorr({ ...corr, reason: e.target.value })} /></Field>
          </div>
          <ErrorNote error={fix.error} />
          <Button className="mt-3" onClick={() => fix.mutate()} loading={fix.isPending} disabled={corr.reason.length < 3}>Save correction</Button>
          {r.corrections.length > 0 && <p className="mt-3 text-sm text-muted">{r.corrections.length} correction(s) recorded.</p>}
        </Panel>
      )}
      {r.consent && <Panel title="Consent and retention"><pre className="font-mono text-xs">{JSON.stringify(r.consent, null, 2)}</pre></Panel>}
    </div>
  );
}
