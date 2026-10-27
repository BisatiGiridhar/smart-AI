import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import Analytics from "./pages/Analytics";
import Architecture from "./pages/Architecture";
import Calibration from "./pages/Calibration";
import Datasets from "./pages/Datasets";
import Evidence from "./pages/Evidence";
import Experiments from "./pages/Experiments";
import Fairness from "./pages/Fairness";
import Jobs from "./pages/Jobs";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Ranking from "./pages/Ranking";
import Resumes from "./pages/Resumes";
import Search from "./pages/Search";
import Security from "./pages/Security";
import Settings from "./pages/Settings";
import Workflow from "./pages/Workflow";

function Protected({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <div className="p-8"><Loading label="Checking your session" /></div>;
  if (!me) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/app" element={<Protected><Layout /></Protected>}>
        <Route index element={<Overview />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:jobId" element={<Jobs />} />
        <Route path="resumes" element={<Resumes />} />
        <Route path="resumes/:resumeId" element={<Resumes />} />
        <Route path="search" element={<Search />} />
        <Route path="ranking" element={<Ranking />} />
        <Route path="ranking/:runId" element={<Ranking />} />
        <Route path="evidence" element={<Evidence />} />
        <Route path="evidence/:resultId" element={<Evidence />} />
        <Route path="workflow" element={<Workflow />} />
        <Route path="fairness" element={<Fairness />} />
        <Route path="security" element={<Security />} />
        <Route path="calibration" element={<Calibration />} />
        <Route path="experiments" element={<Experiments />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="architecture" element={<Architecture />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
