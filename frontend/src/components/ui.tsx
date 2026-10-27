import clsx from "clsx";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { fmt } from "../lib/format";
import type { Task } from "../lib/types";

export function Button({ variant = "primary", className, loading, children, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "quiet"; loading?: boolean }) {
  return (
    <button
      {...p}
      disabled={p.disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-control px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-cyan text-base hover:bg-cyan/90",
        variant === "ghost" && "border border-line bg-transparent text-ink hover:bg-raised",
        variant === "quiet" && "text-muted hover:text-ink",
        variant === "danger" && "border border-danger/50 text-danger hover:bg-danger/10",
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Panel({ title, actions, children, className, subtitle }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-panel border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-1.5 text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const tone: Record<string, string> = {
  neutral: "border-line text-muted",
  cyan: "border-cyan/40 text-cyan bg-cyan/10",
  violet: "border-violet/40 text-violet bg-violet/10",
  amber: "border-amber/40 text-amber bg-amber/10",
  danger: "border-danger/40 text-danger bg-danger/10",
  ok: "border-ok/40 text-ok bg-ok/10",
};
export function Badge({ children, color = "neutral", title }: { children: ReactNode; color?: keyof typeof tone; title?: string }) {
  return <span title={title} className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", tone[color])}>{children}</span>;
}

export function statusColor(s?: string): keyof typeof tone {
  if (!s) return "neutral";
  if (["completed", "succeeded", "supported", "approved", "imported", "available", "reviewed"].includes(s)) return "ok";
  if (["failed", "contradicted", "unavailable"].includes(s)) return "danger";
  if (["needs_review", "pending", "partial", "unsupported", "draft", "not_run", "skipped"].includes(s)) return "amber";
  if (["running", "queued", "importing", "downloading"].includes(s)) return "violet";
  return "neutral";
}
export const StatusBadge = ({ s }: { s?: string }) => <Badge color={statusColor(s)}>{(s ?? "unknown").replace(/_/g, " ")}</Badge>;

export function Field({ label, hint, children, error }: { label: string; hint?: ReactNode; children: ReactNode; error?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}
const control = "w-full rounded-control border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-cyan focus:outline-none";
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={clsx(control, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={clsx(control, "font-sans", p.className)} />;
export function Select({ options, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  return (
    <select {...p} className={clsx(control, p.className)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-panel border border-dashed border-line px-6 py-8">
      <Inbox className="h-5 w-5 text-muted" aria-hidden />
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-xl text-sm text-muted">{children}</div>}
      {action}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{msg}</span>
    </div>
  );
}

export const Loading = ({ label = "Loading" }: { label?: string }) => (
  <div className="flex items-center gap-2 py-6 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{label}</div>
);

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-panel border border-line bg-surface px-4 py-3.5">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </div>
  );
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead><tr className="border-b border-line text-muted">{head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
      {empty && <p className="px-3 py-6 text-sm text-muted">No rows.</p>}
    </div>
  );
}
export const Td = ({ children, className, mono }: { children?: ReactNode; className?: string; mono?: boolean }) => (
  <td className={clsx("px-3 py-2 align-top", mono && "font-mono text-[13px]", className)}>{children}</td>
);

export function TaskBar({ task }: { task?: Task }) {
  if (!task) return null;
  return (
    <div className="space-y-1.5 rounded-control border border-line bg-raised px-3 py-2.5 text-sm" aria-live="polite">
      <div className="flex items-center justify-between gap-2"><span>{task.kind}</span><StatusBadge s={task.status} /></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full bg-cyan transition-all" style={{ width: `${Math.round(task.progress * 100)}%` }} /></div>
      {task.message && <p className="text-xs text-muted">{task.message}</p>}
      {task.error && <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-danger">{task.error}</pre>}
    </div>
  );
}

export const Num = ({ v, d = 3 }: { v?: number | null; d?: number }) => <span className="tabular-nums">{fmt(v ?? null, d)}</span>;

export function SyntheticNotice({ label }: { label?: string }) {
  return (
    <div className="flex items-start gap-2 rounded-control border border-violet/40 bg-violet/10 px-3 py-2 text-sm text-violet">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{label ?? "Public synthetic research dataset — not genuine candidate records."}</span>
    </div>
  );
}

export function DecisionNotice() {
  return <p className="text-sm text-muted">Decision support for qualified human reviewers. Rankings are not hiring decisions, and no applicant is rejected automatically.</p>;
}
