import type { AgentNode } from "../components/Scene3D";

/** Pipeline structure only (mirrors backend/app/core/agents.py). Availability comes from /api/system/agents. */
export const AGENT_STRUCTURE: AgentNode[] = [
  "Resume Extraction", "Job Requirement Analysis", "Hybrid Retrieval", "Candidate Reranking", "Evidence Verification",
  "Candidate Evaluation", "Candidate Ranking", "Multi-Perspective Feedback", "Skill Gap Analysis", "Fairness Audit",
  "Security and Robustness", "Confidence and Calibration",
].map((name, i) => ({ id: `a${i + 1}`, number: i + 1, name }));
