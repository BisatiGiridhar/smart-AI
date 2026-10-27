import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, StatusBadge, SyntheticNotice, Table, TaskBar, Td } from "../components/ui";
import { api } from "../lib/api";
import { when } from "../lib/format";
import { useAuth } from "../lib/auth";
import { useDatasets, useTask } from "../lib/hooks";
import type { DatasetFile, DatasetVersion } from "../lib/types";

type Role = "resumes" | "jobs" | "matches";
const FIELDS: Record<Role, { required: string[]; optional: string[] }> = {
  resumes: { required: ["id", "text"], optional: ["name", "title"] },
  jobs: { required: ["id", "text"], optional: ["title"] },
  matches: { required: ["resume_id", "job_id"], optional: ["id", "label"] },
};
type RoleMap = { file: string; fields: Record<string, string>; label_type: "numeric" | "binary" };

export default function Datasets() {
  const { can } = useAuth();
  const ds = useDatasets();
  const [selected, setSelected] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId);
  const qc = useQueryClient();
  useEffect(() => { if (task.data && ["succeeded", "failed"].includes(task.data.status)) qc.invalidateQueries({ queryKey: ["datasets"] }); }, [task.data, qc]);
  const admin = can("admin");
  return (
    <div className="space-y-6">
      <PageHeader title="Dataset Management" description="Import the published research dataset, check its schema, review rejected rows and create a reproducible split." />
      <SyntheticNotice label={ds.data?.synthetic_label} />
      {admin ? <Sources defaultRepo={ds.data?.default_repo ?? ""} onTask={(t, v) => { setTaskId(t); if (v) setSelected(v); }} /> :
        <p className="text-sm text-muted">Only administrators can import datasets.</p>}
      <TaskBar task={task.data} />
      <Panel title="Dataset versions">
        {ds.isLoading ? <Loading /> : ds.error ? <ErrorNote error={ds.error} /> : !ds.data?.versions.length ? (
          <Empty title="No dataset has been imported">Download the dataset from Hugging Face or upload its files. Counts appear here only after a successful import.</Empty>
        ) : (
          <Table head={["Name", "Method", "Revision", "Status", "Files", "Imported", ""]}>
            {ds.data.versions.map((v) => (
              <tr key={v.id} className={selected === v.id ? "bg-raised" : ""}>
                <Td>{v.name}{v.is_synthetic && <span className="ml-2"><Badge color="violet">synthetic</Badge></span>}</Td>
                <Td>{v.source_method}</Td><Td mono>{v.revision ? v.revision.slice(0, 10) : "—"}</Td>
                <Td><StatusBadge s={v.status} /></Td><Td>{v.files?.length ?? 0}</Td><Td>{when(v.imported_at)}</Td>
                <Td><Button variant="ghost" onClick={() => setSelected(v.id)}>Inspect</Button></Td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
      {selected && <VersionDetail id={selected} admin={admin} onTask={setTaskId} />}
    </div>
  );
}

function Sources({ defaultRepo, onTask }: { defaultRepo: string; onTask: (task: string, version?: string) => void }) {
  const [repo, setRepo] = useState(defaultRepo);
  useEffect(() => setRepo(defaultRepo), [defaultRepo]);
  const [files, setFiles] = useState<FileList | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [license, setLicense] = useState("");
  const [synthetic, setSynthetic] = useState(true);
  const hf = useMutation({ mutationFn: () => api<{ version_id: string; task_id: string }>("/api/datasets/huggingface", { method: "POST", json: { repo_id: repo } }),
    onSuccess: (r) => onTask(r.task_id, r.version_id) });
  const up = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("name", name); fd.append("source_url", url); fd.append("license", license); fd.append("is_synthetic", String(synthetic));
      Array.from(files ?? []).forEach((f) => fd.append("files", f));
      return api<{ version_id: string }>("/api/datasets/upload", { method: "POST", body: fd });
    },
  });
  const qc = useQueryClient();
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Download from Hugging Face" subtitle="Fetches the dataset card and files at a pinned revision. Needs outbound network access from the server.">
        <div className="space-y-3">
          <Field label="Dataset repository"><Input value={repo} onChange={(e) => setRepo(e.target.value)} /></Field>
          <ErrorNote error={hf.error} />
          <Button onClick={() => hf.mutate()} loading={hf.isPending} disabled={!repo}>Download and inspect</Button>
        </div>
      </Panel>
      <Panel title="Upload dataset files" subtitle="CSV, TSV, JSON, JSONL or Parquet, plus the README.md dataset card if you have it.">
        <div className="space-y-3">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="candidate-matching-synthetic" /></Field>
          <Field label="Source URL"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://huggingface.co/datasets/..." /></Field>
          <Field label="License"><Input value={license} onChange={(e) => setLicense(e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} /> These are synthetic research records</label>
          <Field label="Files"><input type="file" multiple accept=".csv,.tsv,.json,.jsonl,.parquet,.md" onChange={(e) => setFiles(e.target.files)} className="text-sm" /></Field>
          <ErrorNote error={up.error} />
          {up.isSuccess && <p className="text-sm text-ok">Files staged. Inspect the new version below to map columns.</p>}
          <Button onClick={() => up.mutate(undefined, { onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }) })} loading={up.isPending} disabled={!files?.length || !name}>Upload and inspect</Button>
        </div>
      </Panel>
    </div>
  );
}

function VersionDetail({ id, admin, onTask }: { id: string; admin: boolean; onTask: (t: string) => void }) {
  const q = useQuery({ queryKey: ["dataset", id], queryFn: () => api<DatasetVersion & { database_counts: Record<string, number>; split_counts: Record<string, Record<string, number>> }>(`/api/datasets/${id}`), refetchInterval: 4000 });
  const rej = useQuery({ queryKey: ["rejected", id], queryFn: () => api<{ total: number; items: { file_name: string; role: string; row_index: number; source_record_id: string | null; reason: string }[]; top_reasons: { reason: string; count: number }[] }>(`/api/datasets/${id}/rejected?size=50`) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const v = q.data!;
  return (
    <div className="space-y-6">
      <Panel title={`Version: ${v.name}`} subtitle={<>Source {v.source_url || "not recorded"}. License {v.license || "not stated in the card"}.</>}>
        <div className="grid gap-3 sm:grid-cols-4">
          {Object.entries(v.database_counts).map(([k, n]) => <div key={k} className="rounded-control border border-line px-3 py-2"><div className="text-xs text-muted">{k} in database</div><div className="text-lg font-semibold tabular-nums">{n.toLocaleString()}</div></div>)}
        </div>
        {v.validation?.errors?.map((e) => <div key={e} className="mt-3"><ErrorNote error={e} /></div>)}
        {v.card_excerpt && <details className="mt-4 text-sm"><summary className="cursor-pointer text-muted">Dataset card excerpt</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs">{v.card_excerpt}</pre></details>}
      </Panel>
      <Panel title="Files and columns" subtitle="Profiles computed from the actual files. Confirm which file and columns hold each record type.">
        {!v.files?.length ? <p className="text-sm text-muted">No readable data files were found.</p> :
          <div className="space-y-4">{v.files.map((f) => <FileProfile key={f.name} f={f} />)}</div>}
      </Panel>
      {admin && v.files?.length > 0 && <MappingForm v={v} onTask={onTask} />}
      {v.status === "imported" && admin && <SplitForm id={v.id} existing={v.split_config} counts={v.split_counts} />}
      <Panel title="Rejected records" subtitle="Rows that failed validation. Nothing is repaired or invented.">
        {!rej.data?.total ? <p className="text-sm text-muted">No rejected rows.</p> : (
          <>
            <ul className="mb-3 space-y-1 text-sm">{rej.data.top_reasons.map((r) => <li key={r.reason}><span className="tabular-nums">{r.count}</span> × {r.reason}</li>)}</ul>
            <Table head={["File", "Role", "Row", "Source id", "Reason"]}>
              {rej.data.items.map((r, i) => <tr key={i}><Td>{r.file_name}</Td><Td>{r.role}</Td><Td>{r.row_index}</Td><Td mono>{r.source_record_id ?? "—"}</Td><Td>{r.reason}</Td></tr>)}
            </Table>
          </>
        )}
      </Panel>
    </div>
  );
}

function FileProfile({ f }: { f: DatasetFile }) {
  return (
    <details className="rounded-control border border-line p-3" open={false}>
      <summary className="cursor-pointer text-sm">
        <span className="font-medium">{f.name}</span> <span className="text-muted">{(f.bytes / 1024 / 1024).toFixed(2)} MB, {f.profile?.rows?.toLocaleString() ?? "?"} rows</span>
        {f.suggestion && <span className="ml-2"><Badge color="cyan">looks like {f.suggestion.role}</Badge></span>}
        {f.error && <span className="ml-2"><Badge color="danger">unreadable</Badge></span>}
      </summary>
      <p className="mt-2 font-mono text-xs text-muted">sha256 {f.sha256}</p>
      {f.error && <ErrorNote error={f.error} />}
      {f.profile && (
        <Table head={["Column", "Type", "Nulls", "Unique", "Avg length", "Sample"]}>
          {f.profile.columns.map((c) => <tr key={c.name}><Td mono>{c.name}</Td><Td>{c.dtype}</Td><Td>{c.null_count}</Td><Td>{c.unique_count}</Td><Td>{c.avg_length}</Td><Td className="max-w-md truncate text-muted">{c.sample[0] ?? ""}</Td></tr>)}
        </Table>
      )}
    </details>
  );
}

function MappingForm({ v, onTask }: { v: DatasetVersion; onTask: (t: string) => void }) {
  const files = v.files.filter((f) => f.profile);
  const initial = (role: Role): RoleMap => {
    const f = files.find((x) => x.suggestion?.role === role);
    return { file: f?.name ?? "", fields: { ...(f?.suggestion?.mapping ?? {}) }, label_type: "numeric" };
  };
  const [m, setM] = useState<Record<Role, RoleMap>>({ resumes: initial("resumes"), jobs: initial("jobs"), matches: initial("matches") });
  const start = useMutation({
    mutationFn: () => {
      const body: Record<string, RoleMap> = { resumes: m.resumes, jobs: m.jobs };
      if (m.matches.file) body.matches = m.matches;
      return api<{ task_id: string }>(`/api/datasets/${v.id}/import`, { method: "POST", json: body });
    },
    onSuccess: (r) => onTask(r.task_id),
  });
  const cols = (file: string) => files.find((f) => f.name === file)?.profile?.columns.map((c) => c.name) ?? [];
  const complete = (["resumes", "jobs"] as Role[]).every((r) => m[r].file && FIELDS[r].required.every((f) => m[r].fields[f]));
  return (
    <Panel title="Column mapping and import" subtitle="Suggestions come from column names only. Check each one. Importing again is safe: existing records are skipped.">
      <div className="grid gap-4 lg:grid-cols-3">
        {(["resumes", "jobs", "matches"] as Role[]).map((role) => (
          <div key={role} className="space-y-2 rounded-control border border-line p-3">
            <p className="font-medium capitalize">{role}{role === "matches" && <span className="text-muted"> (optional)</span>}</p>
            <Field label="File"><Select value={m[role].file} onChange={(e) => setM({ ...m, [role]: { ...m[role], file: e.target.value, fields: {} } })}
              options={[{ value: "", label: "Not used" }, ...files.map((f) => ({ value: f.name, label: f.name }))]} /></Field>
            {m[role].file && [...FIELDS[role].required, ...FIELDS[role].optional].map((field) => (
              <Field key={field} label={`${field}${FIELDS[role].required.includes(field) ? " (required)" : ""}`}>
                <Select value={m[role].fields[field] ?? ""} onChange={(e) => {
                  const fields = { ...m[role].fields };
                  if (e.target.value) fields[field] = e.target.value; else delete fields[field];
                  setM({ ...m, [role]: { ...m[role], fields } });
                }} options={[{ value: "", label: "—" }, ...cols(m[role].file).map((c) => ({ value: c, label: c }))]} />
              </Field>
            ))}
            {role === "matches" && m.matches.file && (
              <Field label="Label type" hint="Numeric labels are min-max normalised for agreement metrics.">
                <Select value={m.matches.label_type} onChange={(e) => setM({ ...m, matches: { ...m.matches, label_type: e.target.value as "numeric" | "binary" } })}
                  options={[{ value: "numeric", label: "Numeric score" }, { value: "binary", label: "Binary match / no match" }]} />
              </Field>
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button onClick={() => start.mutate()} loading={start.isPending} disabled={!complete || v.status === "importing"}>Validate and import</Button>
        {!complete && <span className="text-sm text-muted">Map a file with id and text for both resumes and jobs.</span>}
      </div>
      <div className="mt-3"><ErrorNote error={start.error} /></div>
    </Panel>
  );
}

function SplitForm({ id, existing, counts }: { id: string; existing: Record<string, unknown> | null; counts: Record<string, Record<string, number>> }) {
  const qc = useQueryClient();
  const [seed, setSeed] = useState(42);
  const mut = useMutation({ mutationFn: () => api(`/api/datasets/${id}/split`, { method: "POST", json: { seed, train: 0.7, validation: 0.15, test: 0.15 } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dataset", id] }) });
  return (
    <Panel title="Reproducible split" subtitle="Jobs and resumes linked by matching records are kept in the same split, so nothing leaks between train, validation and test.">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Random seed"><Input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} className="w-32" /></Field>
        <Button onClick={() => mut.mutate()} loading={mut.isPending}>{existing ? "Recreate split" : "Create 70/15/15 split"}</Button>
      </div>
      <ErrorNote error={mut.error} />
      {existing && (
        <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <pre className="overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(existing, null, 2)}</pre>
          <pre className="overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(counts, null, 2)}</pre>
        </div>
      )}
    </Panel>
  );
}
