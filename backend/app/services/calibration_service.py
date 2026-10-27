"""Calibration: fit on validation-split predictions, evaluate on separate test-split predictions."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core import metrics as M
from ..core.calibration import PlattScaler
from ..models import CalibrationRun, ExperimentRun


def _pairs(run: ExperimentRun) -> tuple[list[float], list[int], int]:
    xs, ys, skipped = [], [], 0
    for p in run.predictions or []:
        if p.get("score") is None or not p.get("judged", True) and not run.test_conditions.get("unjudged_treated_as_irrelevant"):
            skipped += 1
            continue
        xs.append(float(p["score"]))
        ys.append(int(p["relevant"]))
    return xs, ys, skipped


def execute(db: Session, params: dict, progress) -> dict:
    cal = db.get(CalibrationRun, params["calibration_id"])
    try:
        val, test = db.get(ExperimentRun, cal.validation_run_id), db.get(ExperimentRun, cal.test_run_id)
        if val.split != "validation" or test.split != "test":
            raise RuntimeError("Calibration needs one experiment run on the validation split and one on the test split.")
        if val.experiment_id != test.experiment_id or val.dataset_version_id != test.dataset_version_id:
            raise RuntimeError("Validation and test runs must use the same experiment and dataset version.")
        if val.config.get("pipeline") != test.config.get("pipeline"):
            raise RuntimeError("Validation and test runs must use the same pipeline configuration.")
        xv, yv, sv = _pairs(val)
        xt, yt, st = _pairs(test)
        scaler = PlattScaler().fit(xv, yv)
        pt = scaler.predict(xt)
        n_bins = int(cal.config.get("bins", 10))
        cal.params = {"a": scaler.a, "b": scaler.b, "validation_n": len(xv), "validation_skipped_no_score": sv}
        cal.metrics = {
            "test_n": len(xt), "test_skipped_no_score": st, "positive_rate_test": (sum(yt) / len(yt)) if yt else None,
            "ece_raw": M.ece(xt, yt, n_bins), "brier_raw": M.brier(xt, yt),
            "ece_calibrated": M.ece(pt, yt, n_bins), "brier_calibrated": M.brier(pt, yt),
            "ece_calibrated_ci95": M.bootstrap_ci(list(zip(pt, yt)), lambda s: M.ece([a for a, _ in s], [b for _, b in s], n_bins), 500),
            "brier_calibrated_ci95": M.bootstrap_ci(list(zip(pt, yt)), lambda s: M.brier([a for a, _ in s], [b for _, b in s]), 500),
            "target": "P(pair is relevant under the dataset label threshold)",
            "note": "Raw S is a rubric score, not a probability. Only the calibrated values are probability estimates, "
                    "and only for this dataset, split and configuration.",
        }
        cal.bins = {"raw": M.reliability_bins(xt, yt, n_bins), "calibrated": M.reliability_bins(pt, yt, n_bins)}
        cal.status = "completed"
        db.commit()
        return {"status": "completed"}
    except Exception as exc:
        db.rollback()
        cal = db.get(CalibrationRun, params["calibration_id"])
        cal.status, cal.error = "failed", f"{type(exc).__name__}: {exc}"
        db.commit()
        raise
