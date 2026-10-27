# Dataset

Initial dataset: **Candidate–Job Matching Synthetic Dataset**, https://huggingface.co/datasets/michaelozon/candidate-matching-synthetic

Label shown throughout the app: *Public synthetic research dataset — not genuine candidate records.*

The listing describes about 10,000 resumes, 2,500 job descriptions and 2,500 matching records. **These figures were not
verified** while building the system, because the build environment had no network access to Hugging Face. The app never
displays the advertised figures. It shows counts queried from the database after an import.

## Import procedure

1. Download (pinned to the repository's commit SHA, which is stored as the revision) or upload the files.
2. Every CSV, TSV, JSON, JSONL and Parquet file is profiled: rows, columns, types, nulls, unique values, samples, SHA-256.
3. A mapping is suggested from column names only. The administrator confirms which file holds resumes, jobs and matches
   and which columns hold ids, text and labels.
4. Validation rejects rows with missing ids or text, duplicate ids, broken resume/job references and unparseable labels.
   Each rejected row is logged with its reason. Nothing is repaired or generated.
5. Imports are idempotent: rows already present for the version are skipped, so a failed import can be retried.

## Split

`app/core/splits.py` builds the bipartite graph of jobs and resumes connected by matching records and assigns whole
connected components to train/validation/test (default 70/15/15), balancing by number of matching records. The seed,
ratios, rule, component count and the dataset revision are stored with the version. No resume or job can appear in two
splits.

## Label assumptions used in experiments

Numeric labels are min-max normalised to [0, 1] over the split. A pair counts as relevant when its normalised label is at
or above the configured threshold (default 0.5). Pools contain the judged resumes for a job plus seeded random negatives
from the same split, which are treated as non-relevant (the usual information-retrieval convention). This assumption is
recorded in each run's test conditions and can be switched off. Whether the published labels reflect independent
recruiter judgement is not established; treat them as the dataset authors' synthetic labels.
