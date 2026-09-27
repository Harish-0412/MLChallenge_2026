#!/usr/bin/env python3
"""Run the SageMaker job entry points locally with their cloud directory contracts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SAMPLE = ROOT / "tmp" / "sagemaker-sample"
RUN = ROOT / "tmp" / "sagemaker-local-run"


def call(*parts, env=None):
    process_env = (env or os.environ).copy()
    existing = process_env.get("PYTHONPATH", "")
    process_env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), str(ROOT / "src"), existing)))
    subprocess.run([PYTHON, *map(str, parts)], cwd=ROOT, env=process_env, check=True)


def main() -> int:
    call("scripts/make_sagemaker_sample_inputs.py", "--replace")
    if RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True)
    pairs = RUN / "pairs"
    call(
        "cloud/sagemaker/jobs/build_pair_sets.py", "--features", SAMPLE / "features" / "feat_v2_0",
        "--candidates", SAMPLE / "candidates" / "candidate_v1", "--output", pairs,
        "--mode", "sample", "--experiment-id", "local-smoke", "--threads", "1",
    )
    env = os.environ.copy()
    env.update({
        "SM_CHANNEL_TRAIN": str(pairs / "train"),
        "SM_CHANNEL_EARLY_STOP": str(pairs / "early-stop"),
        "SM_CHANNEL_CALIBRATION": str(pairs / "calibration"),
        "SM_CHANNEL_CALIBRATION_TRUTH": str(SAMPLE / "labels" / "fold_v1" / "calibration"),
        "SM_MODEL_DIR": str(RUN / "model"), "SM_OUTPUT_DATA_DIR": str(RUN / "training-output"),
    })
    call("cloud/sagemaker/jobs/train_gbdt.py", "--experiment-id", "local-smoke", "--n-estimators", "60", env=env)
    model_input = RUN / "model-input"
    model_input.mkdir()
    with tarfile.open(model_input / "model.tar.gz", "w:gz") as bundle:
        for path in sorted((RUN / "model").iterdir()):
            bundle.add(path, arcname=path.name)
    evaluation = RUN / "evaluation"
    call(
        "cloud/sagemaker/jobs/evaluate.py", "--model", model_input, "--pairs", pairs / "holdout",
        "--truth", SAMPLE / "labels" / "fold_v1" / "holdout" / "truth",
        "--slices", SAMPLE / "labels" / "fold_v1" / "holdout" / "slices",
        "--output", evaluation, "--experiment-id", "local-smoke",
    )
    submission = RUN / "submission"
    call(
        "cloud/sagemaker/jobs/export_predictions.py", "--model", model_input, "--pairs", pairs / "test",
        "--required", SAMPLE / "labels" / "fold_v1" / "test" / "required", "--output", submission,
    )
    if not (submission / "matching_results.tsv").is_file() or not (submission / "candidate_pairs.tsv").is_file():
        raise RuntimeError("local smoke did not create both submission files")
    print(f"LOCAL_SAGEMAKER_SMOKE_PASS {evaluation / 'evaluation.json'} {submission}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
