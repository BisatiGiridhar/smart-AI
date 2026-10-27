# Implementation status

This file separates what was verified from what was written but not executed in the build environment, which had no
access to PyPI downloads, npm or Hugging Face.

## Verified by running tests (34 pass, 1 skipped without FastAPI)

- BM25, RRF formula and tie handling
- Scoring formulas S, C, S_low, S_high; insufficient-evidence handling; weight validation
- Citation verification (exact, whitespace-tolerant, location mismatch, not found)
- Resume and job parsers with provenance; rubric drafting
- Deterministic evaluator, citation downgrading, skill gaps
- Injection detection and untrusted wrapping; counterfactual substitution and flip rate
- All metrics, bootstrap CI, Platt calibration
- Leakage-free component split; dataset mapping suggestion and row validation
- Text extraction for TXT, DOCX, text PDFs and scanned PDFs through tesseract OCR
- Sequential pipeline with unavailable dense and rerank stages reported as partial or skipped; experiment runner B, C (not run), D, J

## Written, checked statically, not executed

- FastAPI routers, SQLAlchemy models, Alembic baseline, background tasks (checked for undefined names, model-field
  mismatches and serializer fields)
- API integration test `tests/test_api.py` (runs once dependencies are installed)
- LangGraph execution path, Sentence Transformers, CrossEncoder and ChromaDB integration, Hugging Face download
- LLM adapters (OpenAI-compatible, Anthropic, Ollama)
- React front end (type-checked against stub declarations of the external libraries; not built or viewed in a browser)
- Docker images and Compose file

## Not implemented

- LLM-based resume extraction and LLM rubric drafting (deterministic versions exist; the adapter is ready)
- Annotation workflow for evidence faithfulness and precision (paper Section V-B); these metrics need human labels
- Worst-group error gap on real group labels (computed only when an auditor supplies authorized group labels)
- Multi-instance rate limiting and task queue

## Measured results

None yet. Run the experiments on your hardware and record the test conditions shown with each run.
