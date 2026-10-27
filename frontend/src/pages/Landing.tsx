import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { AgentScene } from "../components/Scene3D";
import { api } from "../lib/api";
import { AGENT_STRUCTURE } from "../lib/agents";
import { useAuth } from "../lib/auth";

const STAGES = [
  ["Keyword retrieval", "BM25 over resume text finds exact skills and tools."],
  ["Semantic retrieval", "Sentence embeddings find matches written in different words."],
  ["Fusion and reranking", "Reciprocal Rank Fusion merges both lists; a cross-encoder reorders the shortlist."],
  ["Evidence verification", "Every claim must quote the resume at the stated location, or it is rejected."],
  ["Scoring with coverage", "A versioned rubric gives a recomputable score and shows how much of it is verified."],
  ["Human review", "Uncertain or flagged cases go to a reviewer. Nothing is rejected automatically."],
];

export default function Landing() {
  const { me } = useAuth();
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<{ status: string; database: boolean }>("/api/health"), retry: false });
  return (
    <div className="min-h-full bg-base">
      <header className="mx-auto flex max-w-[1240px] items-center justify-between px-6 py-5">
        <span className="font-semibold">Smart AI Hiring Assistant</span>
        <Link to={me ? "/app" : "/login"} className="rounded-control border border-line px-3.5 py-2 text-sm hover:bg-raised">{me ? "Open dashboard" : "Sign in"}</Link>
      </header>
      <section className="mx-auto grid max-w-[1240px] items-center gap-8 px-6 pb-10 pt-6 lg:grid-cols-[1.05fr_1fr]">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <h1 className="text-[clamp(2rem,4.2vw,3.35rem)] font-semibold leading-[1.08]">
            Smart AI Hiring Assistant Using Multi-Agent LLMs and Retrieval-Augmented Generation
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted">Smarter Recruitment. Explainable Decisions. Evidence-Based Hiring.</p>
          <p className="mt-4 max-w-xl text-muted">
            Twelve cooperating agents and services retrieve, verify and score candidates against a recruiter-approved rubric, then hand every decision to a person.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link to={me ? "/app" : "/login"} className="rounded-control bg-cyan px-4 py-2.5 text-sm font-medium text-base hover:bg-cyan/90">{me ? "Open dashboard" : "Sign in to your workspace"}</Link>
            <span className="text-sm text-muted">API {health.isLoading ? "checking" : health.data?.status === "ok" ? "online" : "not reachable"}</span>
          </div>
        </motion.div>
        <div className="relative">
          <AgentScene agents={AGENT_STRUCTURE} documents={0} height={460} />
          <p className="mt-1 text-center text-xs text-muted">Pipeline structure. Live status and data appear after sign-in.</p>
        </div>
      </section>
      <section className="mx-auto max-w-[1240px] px-6 pb-16">
        <h2 className="mb-4 text-lg font-semibold">How a screening run works</h2>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STAGES.map(([t, d], i) => (
            <li key={t} className="rounded-panel border border-line bg-surface p-4">
              <p className="text-sm text-cyan">Stage {i + 1}</p>
              <p className="mt-1 font-medium">{t}</p>
              <p className="mt-1 text-sm text-muted">{d}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
