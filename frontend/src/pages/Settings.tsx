import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, Table, Td } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { short, when } from "../lib/format";
import { Pager } from "./Jobs";

export default function Settings() {
  const { me, can } = useAuth();
  const status = useQuery({ queryKey: ["sysstatus"], queryFn: () => api<Record<string, unknown>>("/api/system/status") });
  return (
    <div className="space-y-6">
      <PageHeader title="Settings and Audit Logs" description="Workspace members, runtime configuration and the record of sensitive actions." />
      <Panel title="Your account"><p className="text-sm">{me?.email}, role {me?.role}, in {me?.memberships.find((m) => m.workspace_id === me.active_workspace_id)?.workspace_name}.</p></Panel>
      <Panel title="Runtime configuration" subtitle="Model, provider and storage settings come from server environment variables; API keys never reach the browser.">
        {status.isLoading ? <Loading /> : status.error ? <ErrorNote error={status.error} /> : <pre className="overflow-auto rounded-control bg-raised p-3 font-mono text-xs">{JSON.stringify(status.data, null, 2)}</pre>}
      </Panel>
      {can("admin") ? <><Members /><Workspaces /><AuditLog /></> : <p className="text-sm text-muted">Member management and audit logs are visible to administrators.</p>}
    </div>
  );
}

function Members() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["members"], queryFn: () => api<{ user_id: string; email: string; full_name: string; role: string; active: boolean }[]>("/api/auth/members") });
  const [f, setF] = useState({ email: "", full_name: "", password: "", role: "recruiter" });
  const add = useMutation({ mutationFn: () => api("/api/auth/members", { method: "POST", json: { ...f, password: f.password || null } }), onSuccess: () => { setF({ ...f, email: "", full_name: "", password: "" }); qc.invalidateQueries({ queryKey: ["members"] }); } });
  return (
    <Panel title="Members">
      {q.data && <Table head={["Email", "Name", "Role"]}>{q.data.map((m) => <tr key={m.user_id}><Td>{m.email}</Td><Td>{m.full_name}</Td><Td>{m.role}</Td></tr>)}</Table>}
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <Field label="Email"><Input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Name"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label="Initial password" hint="New users only; 12+ characters."><Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label="Role"><Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} options={["admin", "recruiter", "researcher", "reviewer"].map((r) => ({ value: r, label: r }))} /></Field>
      </div>
      <ErrorNote error={add.error} />
      <Button className="mt-3" onClick={() => add.mutate()} loading={add.isPending} disabled={!f.email}>Add or update member</Button>
    </Panel>
  );
}

function Workspaces() {
  const { me } = useAuth();
  const [name, setName] = useState("");
  const create = useMutation({ mutationFn: () => api("/api/auth/workspaces", { method: "POST", json: { name } }), onSuccess: () => window.location.reload() });
  return (
    <Panel title="Workspaces" subtitle="Each workspace's resumes, jobs, audits and experiments are isolated from the others.">
      <ul className="mb-3 text-sm">{me?.memberships.map((m) => <li key={m.workspace_id}>{m.workspace_name} ({m.role})</li>)}</ul>
      <div className="flex flex-wrap items-end gap-3"><Field label="New workspace name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field><Button onClick={() => create.mutate()} disabled={!name} loading={create.isPending}>Create workspace</Button></div>
      <ErrorNote error={create.error} />
    </Panel>
  );
}

function AuditLog() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const q = useQuery({ queryKey: ["audit", page, action], queryFn: () => api<{ total: number; items: { id: string; user_id: string | null; action: string; target_type: string | null; target_id: string | null; details: Record<string, unknown>; ip: string | null; created_at: string }[] }>(`/api/audit-logs?page=${page}&size=50&action=${encodeURIComponent(action)}`) });
  return (
    <Panel title="Audit log" actions={<Input aria-label="Filter by action" placeholder="Filter by action prefix" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} className="w-56" />}>
      {q.isLoading ? <Loading /> : q.error ? <ErrorNote error={q.error} /> : (
        <>
          <Table head={["When", "Action", "User", "Target", "Details", "IP"]}>
            {q.data!.items.map((a) => <tr key={a.id}><Td className="whitespace-nowrap">{when(a.created_at)}</Td><Td mono>{a.action}</Td><Td mono>{short(a.user_id)}</Td><Td>{a.target_type ?? ""} <span className="font-mono text-xs">{short(a.target_id)}</span></Td><Td className="max-w-md truncate font-mono text-xs text-muted">{JSON.stringify(a.details)}</Td><Td>{a.ip}</Td></tr>)}
          </Table>
          <Pager page={page} total={q.data!.total} size={50} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}
