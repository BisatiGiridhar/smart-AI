# Architecture

## Request path

React front end, then the FastAPI API (JWT auth, server-side role checks, workspace filter on every query, rate limit,
audit log), then background tasks (dataset import, indexing, evaluation runs, audits, experiments) stored in the
`background_tasks` table so progress and failures are visible.

## Screening pipeline (one evaluation run)

The nodes are plain Python functions in `app/core/pipeline.py`. They run in a LangGraph `StateGraph` when LangGraph is
installed, otherwise in an explicit sequential executor. The run records which one was used, and stores one
`agent_executions` row per node with its status (`completed`, `partial`, `skipped`, `failed`), duration and detail.

| Order | Node | Agent(s) | Implementation |
|---|---|---|---|
| 1 | job_requirement_analysis | 2 | Validates the approved rubric and builds the retrieval query |
| 2 | hybrid_retrieval | 3 | BM25 (own implementation) + dense search (ChromaDB) fused by RRF, k configurable |
| 3 | candidate_reranking | 4 | Cross-encoder on the top of the fused list; skipped and reported when unavailable |
| 4 | resume_extraction | 1 | Reuses stored structured extraction, parses when missing |
| 5 | candidate_evaluation | 6 | Deterministic evidence matching, or LLM judgement with schema validation |
| 6 | evidence_verification | 5 | Every quote must exist at its stated location in the same resume |
| 7 | candidate_ranking | 7 | Deterministic S, coverage and bounds; ranking policy configurable |
| 8 | feedback_and_skill_gaps | 8, 9 | Three analytical perspectives and gap list from the same evidence |

Agents 10 to 12 (fairness, security, calibration) run as separate jobs and never change stored scores.

## Scoring

For criterion *i*: s_i = r_i / R_i. With V the verified criteria and U the unverified ones, and weights normalised to sum to 1:

- S = sum over V of w_i s_i, divided by the sum over V of w_i (normalised verified score)
- C = sum over V of w_i (evidence coverage)
- S_low = sum over V of w_i s_i; S_high = S_low + sum over U of w_i

When V is empty, S is not computed ("Insufficient evidence") and the result goes to review. Missing evidence is never
scored as zero and never described as lack of skill.

## Data separation

`resumes.source_kind` is `synthetic_research` or `genuine`. Every corpus key is either `genuine` or
`dataset:<version id>`, and the loader filters on it, so the two are never mixed. Genuine resumes need consent metadata
to enter a corpus. Researchers cannot open genuine records.
