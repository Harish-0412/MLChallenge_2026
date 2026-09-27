import json
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cloud.sagemaker.budget import load_ledger, reserve  # noqa: E402
from cloud.sagemaker.foundation import (  # noqa: E402
    BudgetPolicy, FoundationError, JobEstimate, S3Layout, assert_caller_matches_config,
    assert_safe_caller, load_foundation_config,
)
from cloud.sagemaker.metrics import METRIC_NAMES, TRAINING_METRIC_DEFINITIONS  # noqa: E402
from cloud.sagemaker.pipeline import build_pipeline  # noqa: E402


def config():
    value = json.loads((ROOT / "configs" / "sagemaker.sample.json").read_text(encoding="utf-8"))
    value["bucket"] = "sagemaker-er-test-123456789012"
    value["role_arn"] = "arn:aws:iam::123456789012:role/SageMakerEntityResolution"
    value["images"] = {
        "cpu": "123456789012.dkr.ecr.us-east-1.amazonaws.com/er-cpu:test",
        "neural": "123456789012.dkr.ecr.us-east-1.amazonaws.com/er-neural:test",
    }
    return value


class FoundationTests(unittest.TestCase):
    def test_s3_layout_is_versioned_and_rejects_unsafe_segments(self):
        layout = S3Layout("safe-bucket", "entity-resolution")
        self.assertEqual(layout.versioned("features", "feat_v2_0"), "s3://safe-bucket/entity-resolution/features/feat_v2_0")
        with self.assertRaises(FoundationError):
            layout.versioned("features", "../escape")

    def test_root_credentials_are_blocked(self):
        with self.assertRaisesRegex(FoundationError, "root credentials"):
            assert_safe_caller({"Arn": "arn:aws:iam::123456789012:root"})
        assert_safe_caller({"Arn": "arn:aws:sts::123456789012:assumed-role/Deploy/session"})

    def test_caller_account_must_match_role_and_ecr(self):
        value = config()
        assert_caller_matches_config({"Account": "123456789012"}, value)
        with self.assertRaisesRegex(FoundationError, "differs from configured account"):
            assert_caller_matches_config({"Account": "999999999999"}, value)

    def test_placeholder_config_is_rejected_and_complete_config_loads(self):
        with self.assertRaisesRegex(FoundationError, "REPLACE"):
            load_foundation_config(ROOT / "configs" / "sagemaker.sample.json")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config.json"
            path.write_text(json.dumps(config()), encoding="utf-8")
            self.assertEqual(load_foundation_config(path)["region"], "us-east-1")

    def test_budget_reserves_contingency_and_single_job_cap(self):
        policy = BudgetPolicy(Decimal("200"), Decimal("40"), {"gbdt": Decimal("35")}, Decimal("20"), Decimal("25"))
        safe = JobEstimate("job-1", "gbdt", "ml.r5.xlarge", 1, 3600, Decimal("5"))
        policy.check_job(safe)
        too_large = JobEstimate("job-2", "gbdt", "ml.r5.xlarge", 1, 3600, Decimal("21"))
        with self.assertRaisesRegex(FoundationError, "single-job cap"):
            policy.check_job(too_large)

    def test_budget_ledger_is_atomic_and_refuses_duplicate_job(self):
        policy = BudgetPolicy(Decimal("200"), Decimal("40"), {"gbdt": Decimal("35")}, Decimal("20"), Decimal("25"))
        estimate = JobEstimate("job-1", "gbdt", "ml.x", 1, 1800, Decimal("4"))
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ledger.json"
            reserve(path, policy, estimate)
            self.assertEqual(load_ledger(path)["entries"][0]["estimated_usd"], "2.00")
            with self.assertRaisesRegex(FoundationError, "already contains"):
                reserve(path, policy, estimate)

    def test_every_required_cloudwatch_metric_has_a_definition(self):
        regex_names = {item["regex"].split("=")[0].removeprefix("METRIC ") for item in TRAINING_METRIC_DEFINITIONS}
        self.assertEqual(regex_names, set(METRIC_NAMES))

    def test_pipeline_definition_has_gates_timeouts_and_no_endpoint(self):
        definition = json.loads(build_pipeline(config(), mode="sample", offline=True).definition())
        text = json.dumps(definition)
        self.assertEqual([step["Name"] for step in definition["Steps"]], ["CandidateQuality", "CandidateQualityGate"])
        for expected in ("BuildPairSets", "TrainCalibratedGBDT", "EvaluateLockedHoldout", "ModelQualityGate", "ExportSubmission"):
            self.assertIn(expected, text)
        self.assertIn("MaxRuntimeInSeconds", text)
        self.assertIn("PipelineExecutionId", text)
        self.assertNotIn('"key":', text)
        self.assertIn('"Key": "Project"', text)
        self.assertNotIn("EndpointConfig", text)
        self.assertNotIn("CreateModel", text)


if __name__ == "__main__":
    unittest.main()
