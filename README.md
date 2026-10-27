# Smart AI Hiring Assistant Using Multi-Agent LLMs and Retrieval-Augmented Generation

**Smart AI Hiring Assistant (SAIHA).** Smarter Recruitment. Explainable Decisions. Evidence-Based Hiring.

A full-stack recruitment decision-support system. Twelve logical agents and services retrieve candidates with hybrid
search (BM25 + dense vectors + Reciprocal Rank Fusion + cross-encoder reranking), verify every evidence quote against the
resume, score each candidate with a recruiter-approved, versioned rubric, and send uncertain cases to a human reviewer.
Fairness, security and calibration modules run alongside the scoring path and are isolated from it.

The system never rejects an applicant automatically.

## Quick start (Docker)

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and JWT_SECRET (32+ characters)
docker compose up --build
```

Open http://localhost:8080. The first visit shows a setup screen that creates the administrator account.
API documentation (OpenAPI) is at http://localhost:8000/docs.

Set `INSTALL_ML=false` in `.env` for a smaller image without PyTorch. Dense retrieval and reranking are then reported as
unavailable, and BM25-only screening still works.

## Local development

```bash
# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt -r requirements-dev.txt
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
alembic upgrade head                    # SQLite at ./data/saiha.db unless DATABASE_URL is set
uvicorn app.main:app --reload

# frontend (second terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

Run the tests with `pytest -q` in `backend/`.

## First research workflow

1. **Dataset Management:** download `michaelozon/candidate-matching-synthetic` (or upload its files). Inspect the column
   profiles, confirm the mapping for resumes, jobs and matching records, and import.
   Then create a split (seed recorded).
2. **Hybrid Candidate Search:** build the vector index for the dataset corpus.
3. **Research Experiment Lab:** run experiments B, D, G, H, I and J (A needs an LLM; C, E and F need the embedding and
   cross-encoder models). Run the same experiment on the validation split too.
4. **Confidence and Calibration:** pair the validation and test runs to fit and evaluate calibration.
5. **Analytics and Reports:** export the CSV and copy measured values, with test conditions, into the paper.

## Recruiting workflow (genuine records)

Add a job on **Job Descriptions**, re-analyze it to draft a rubric, edit the weights, save and approve it. Upload resumes on
**Resume Management** with a lawful basis, consent reference and retention date. Run an evaluation on **Candidate
Ranking**, inspect evidence on **Evidence Explorer** and record a reviewer decision.

## Repository layout

```
backend/app/core       framework-free logic: BM25, RRF, scoring, evidence, parsers, metrics, splits, pipeline, experiments
backend/app/services   database-aware services: importer, screening, LLM adapters, models, fairness, security, calibration
backend/app/api        FastAPI routers
backend/tests          unit tests (core) and API integration tests
frontend/src/pages     the 15 application pages plus landing and sign-in
docs/                  architecture, dataset, experiments, security and implementation status
```

See `docs/IMPLEMENTATION_STATUS.md` for what has and has not been verified.
