# Experiments

The master prompt text ends at experiment F; configurations G to J follow Table III of the accompanying paper draft.

| ID | Configuration | Changed factor |
|---|---|---|
| A | Single-LLM baseline | One prompt scores each pair; needs an LLM |
| B | Multi-agent, no retrieval | Whole pool evaluated, no retrieval stage |
| C | Dense-vector RAG | Shortlist from dense retrieval only |
| D | BM25-only retrieval | Shortlist from BM25 only |
| E | Hybrid BM25 + vector | RRF shortlist |
| F | Hybrid + cross-encoder | RRF shortlist reranked |
| G | Complete framework | All agents |
| H | Without extraction agent | Raw-text matching on criterion labels, no aliases |
| I | Without evidence verification | Citations accepted unchecked |
| J | Under adversarial inputs | Instruction injection and keyword stuffing appended to non-relevant pool members |

All runs share dataset version, split, pools, seed and rubric source. If a job has no approved rubric, the rubric is
auto-drafted from the job text and the run records this.

**Metrics.** Agreement (Pearson, Spearman, MAE, RMSE) between S and normalised labels on judged pairs; nDCG@10,
precision@K, recall@K, MRR and Kendall's tau per job with 95% bootstrap CIs over jobs; retrieval recall at the shortlist
size; P95 seconds per job; cost per resume when token prices are configured. Experiment J adds attack success and
detection rates per attack type. Paired comparisons use the Wilcoxon signed-rank test on per-job values.

**Expected limitations to report.** With the deterministic evaluator, I differs from G only when citations could be
wrong, which happens mainly with the LLM evaluator. Keyword stuffing is not detected by the injection screen; it is a
content-manipulation attack that the deterministic matcher is vulnerable to by design. Evidence faithfulness, precision
and coverage as defined in the paper need human annotation and are not computed automatically.
