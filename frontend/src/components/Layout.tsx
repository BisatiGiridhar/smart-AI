import clsx from "clsx";
import {
  Activity, BarChart3, Boxes, Briefcase, Database, FileSearch, FileText, FlaskConical, Gauge, LayoutDashboard,
  ListOrdered, LogOut, Menu, Moon, Network, Scale, Search, Settings, ShieldCheck, Sun, X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";

type Item = { to: string; label: string; icon: typeof Activity };
const GROUPS: { label: string; items: Item[] }[] = [
  { label: "Workspace", items: [
    { to: "/app", label: "Overview Dashboard", icon: LayoutDashboard },
    { to: "/app/datasets", label: "Dataset Management", icon: Database },
    { to: "/app/jobs", label: "Job Descriptions", icon: Briefcase },
    { to: "/app/resumes", label: "Resume Management", icon: FileText },
  ] },
  { label: "Screening", items: [
    { to: "/app/search", label: "Hybrid Candidate Search", icon: Search },
    { to: "/app/ranking", label: "Candidate Ranking", icon: ListOrdered },
    { to: "/app/evidence", label: "Evidence Explorer", icon: FileSearch },
    { to: "/app/workflow", label: "Multi-Agent Workflow", icon: Network },
  ] },
  { label: "Assurance", items: [
    { to: "/app/fairness", label: "Fairness Audit", icon: Scale },
    { to: "/app/security", label: "Security and Robustness", icon: ShieldCheck },
    { to: "/app/calibration", label: "Confidence and Calibration", icon: Gauge },
  ] },
  { label: "Research", items: [
    { to: "/app/experiments", label: "Research Experiment Lab", icon: FlaskConical },
    { to: "/app/analytics", label: "Analytics and Reports", icon: BarChart3 },
  ] },
  { label: "System", items: [
    { to: "/app/architecture", label: "System Architecture", icon: Boxes },
    { to: "/app/settings", label: "Settings and Audit Logs", icon: Settings },
  ] },
];

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="space-y-5">
      {GROUPS.map((g) => (
        <div key={g.label}>
          <p className="px-3 pb-1 text-xs font-medium text-muted">{g.label}</p>
          <ul className="space-y-0.5">
            {g.items.map((it) => (
              <li key={it.to}>
                <NavLink
                  to={it.to}
                  end={it.to === "/app"}
                  onClick={onNavigate}
                  className={({ isActive }) => clsx("flex items-center gap-2.5 rounded-control px-3 py-1.5 text-sm transition-colors",
                    isActive ? "bg-cyan/10 text-ink shadow-[inset_2px_0_0_rgb(var(--cyan))]" : "text-muted hover:bg-raised hover:text-ink")}
                >
                  <it.icon className="h-4 w-4 shrink-0" aria-hidden />
                  {it.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Layout() {
  const { me, logout, switchWorkspace } = useAuth();
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const Shell = ({ children }: { children: ReactNode }) => <div className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5">{children}</div>;
  const brand = (
    <div className="px-3">
      <p className="text-[15px] font-semibold">Smart AI Hiring Assistant</p>
      <p className="text-xs text-muted">SAIHA</p>
    </div>
  );
  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-line bg-surface lg:block"><Shell>{brand}<Nav /></Shell></aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <button aria-label="Close menu" className="absolute inset-0 bg-base/70" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-72 border-r border-line bg-surface">
            <button aria-label="Close menu" onClick={() => setOpen(false)} className="absolute right-3 top-4 text-muted"><X className="h-5 w-5" /></button>
            <Shell>{brand}<Nav onNavigate={() => setOpen(false)} /></Shell>
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex items-center gap-3 border-b border-line px-4 py-2.5 sm:px-6">
          <button className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <div className="flex-1" />
          {me && me.memberships.length > 1 && (
            <select aria-label="Workspace" value={me.active_workspace_id} onChange={(e) => switchWorkspace(e.target.value)}
              className="rounded-control border border-line bg-raised px-2 py-1 text-sm">
              {me.memberships.map((m) => <option key={m.workspace_id} value={m.workspace_id}>{m.workspace_name}</option>)}
            </select>
          )}
          {me && <span className="hidden text-sm text-muted sm:inline">{me.email} ({me.role})</span>}
          <button onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} className="rounded-control p-1.5 text-muted hover:text-ink">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button onClick={logout} className="flex items-center gap-1.5 rounded-control px-2 py-1.5 text-sm text-muted hover:text-ink"><LogOut className="h-4 w-4" />Sign out</button>
        </header>
        <main className="mx-auto w-full max-w-[1240px] flex-1 px-4 py-7 sm:px-6"><Outlet /></main>
      </div>
    </div>
  );
}
