import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "student_resource" / "utils"))

from modeling.calibration import fit_calibrator  # noqa: E402
from modeling.contracts import QueryDecision, ScoredPair  # noqa: E402
from modeling.decision import DecisionPolicy, decide_queries, search_policy  # noqa: E402
from modeling.export import export_submission  # noqa: E402
from modeling.evaluation import evaluate_slices  # noqa: E402
from modeling.inference import score_pair_table  # noqa: E402
from modeling.models import GBDTConfig, train_gbdt  # noqa: E402
from modeling.pair_features import FEATURE_COLUMNS, PAIR_SCHEMA, feature_matrix  # noqa: E402
from modeling.sampling import sample_training_pairs  # noqa: E402
from validate_submission import validate as validate_submission  # noqa: E402


class ModelingPipelineTests(unittest.TestCase):
    def test_decisions_include_empty_queries_and_are_deterministic(self):
        pairs = [ScoredPair("S1-1", "S2-2", .8), ScoredPair("S1-1", "S2-1", .8)]
        policy = DecisionPolicy(threshold=.9, top_k=2)
        first = decide_queries(pairs, ["S1-1", "S1-2"], policy)
        second = decide_queries(reversed(pairs), ["S1-2", "S1-1"], policy)
        self.assertEqual(first, second)
        self.assertEqual(first[1].matched_entity_ids, ())

    def test_policy_search_optimizes_macro_f05(self):
        truth = {"S1-1": ("S2-1",), "S1-2": (), "S1-3": ("S3-1",)}
        pairs = [
            ScoredPair("S1-1", "S2-1", .9), ScoredPair("S1-1", "S2-2", .4),
            ScoredPair("S1-2", "S2-3", .3), ScoredPair("S1-3", "S3-1", .8),
        ]
        policy, score = search_policy(pairs, truth, thresholds=[.2, .5, .85], top_ks=[1, 2])
        self.assertEqual(score, 1.0)
        self.assertEqual(policy.threshold, .5)

    def test_calibration_rejects_query_overlap(self):
        with self.assertRaisesRegex(ValueError, "leakage"):
            fit_calibrator(np.array([.1, .9]), np.array([0, 1]), method="platt", model_fit_query_ids=["S1-1"], calibration_query_ids=["S1-1"])

    def test_export_enforces_candidate_subset(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "absent from candidates"):
                export_submission([QueryDecision("S1-1", ("S2-9",))], {"S1-1": ("S2-1",)}, ["S1-1"], Path(raw))

    def test_successful_export_includes_empty_query(self):
        with tempfile.TemporaryDirectory() as raw:
            matching, candidates = export_submission(
                [QueryDecision("S1-1", ("S2-1",)), QueryDecision("S1-2", ())],
                {"S1-1": ("S2-1", "S3-1"), "S1-2": ()}, ["S1-1", "S1-2"], Path(raw),
            )
            self.assertEqual(matching.read_text().splitlines()[-1], "S1-2\t")
            self.assertTrue(candidates.is_file())

    def test_export_passes_official_validator(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            test_dir, output_dir = root / "test", root / "output"
            test_dir.mkdir()
            (test_dir / "test_source1.tsv").write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\nS1-1\tA\tX\tIndia\nS1-2\tB\tY\tIndia\n",
                encoding="utf-8",
            )
            matching, candidates = export_submission(
                [QueryDecision("S1-1", ("S2-1",)), QueryDecision("S1-2", ())],
                {"S1-1": ("S2-1",), "S1-2": ()}, ["S1-1", "S1-2"], output_dir,
            )
            errors, _ = validate_submission(str(matching), str(candidates), str(test_dir), check_ids=False)
            self.assertEqual(errors, [])

    def test_hard_negative_sampling_is_deterministic_and_weighted(self):
        rows = [{"s1_entity_id": "S1-1", "candidate_entity_id": "S2-0", "is_positive": 1, "evidence_slice": "positive"}]
        rows += [
            {"s1_entity_id": "S1-1", "candidate_entity_id": f"S2-{i}", "is_positive": 0,
             "evidence_slice": "name" if i % 2 else "address"} for i in range(1, 21)
        ]
        first = sample_training_pairs(rows, negatives_per_positive=4, minimum_negatives=0, seed=9)
        second = sample_training_pairs(reversed(rows), negatives_per_positive=4, minimum_negatives=0, seed=9)
        self.assertEqual(first, second)
        self.assertEqual(sum(row["is_positive"] == 0 for row in first), 4)
        self.assertTrue(all(row["sample_weight"] == 5.0 for row in first if row["is_positive"] == 0))

    def test_slice_report_includes_overlapping_groups(self):
        truth = {"S1-1": ("S2-1",), "S1-2": ()}
        pred = {"S1-1": ("S2-1",), "S1-2": ()}
        report = evaluate_slices(truth, pred, {"S1-1": ("India", "cross_script"), "S1-2": ("India", "singleton")})
        self.assertEqual(report["all"]["macro_f05"], 1.0)
        self.assertEqual(report["India"]["queries"], 2)

    def test_both_gbdt_backends_and_calibration(self):
        rng = np.random.default_rng(7)
        width = len(FEATURE_COLUMNS)
        x = rng.normal(size=(120, width)).astype("float32")
        y = (x[:, 0] + x[:, 1] * .5 > 0).astype("int8")
        train_x, train_y = x[:70], y[:70]
        val_x, val_y = x[70:95], y[70:95]
        cal_x, cal_y = x[95:], y[95:]
        for backend in ("xgboost", "lightgbm"):
            config = GBDTConfig(backend=backend, n_estimators=40, early_stopping_rounds=5, n_jobs=1)
            model = train_gbdt(train_x, train_y, val_x, val_y, config=config)
            raw_scores = model.predict_proba(cal_x)
            calibrator = fit_calibrator(
                raw_scores, cal_y, method="platt",
                model_fit_query_ids=[f"S1-{i}" for i in range(95)],
                calibration_query_ids=[f"S1-{i}" for i in range(95, 120)],
            )
            calibrated = calibrator.predict(raw_scores)
            self.assertEqual(calibrated.shape, (25,))
            self.assertTrue(np.all((calibrated >= 0) & (calibrated <= 1)))

    def test_pair_table_to_model_to_export_vertical_slice(self):
        rng = np.random.default_rng(41)

        def table(start, count, labeled=True):
            rows = []
            for index in range(start, start + count):
                positive = index % 2
                features = {name: float(rng.normal()) for name in FEATURE_COLUMNS}
                features[FEATURE_COLUMNS[0]] = float(positive)
                rows.append({
                    "s1_entity_id": f"S1-{index}", "candidate_entity_id": f"S2-{index}", "country": "OpenCountry",
                    "evidence_slice": "strong" if positive else "weak", "is_positive": positive if labeled else -1,
                    "sample_weight": 1.0, **features,
                })
            return pa.Table.from_pylist(rows, schema=PAIR_SCHEMA)

        train, validation, inference = table(1, 50), table(51, 20), table(71, 6, labeled=False)
        model = train_gbdt(
            feature_matrix(train), train["is_positive"].to_numpy(), feature_matrix(validation), validation["is_positive"].to_numpy(),
            config=GBDTConfig(backend="xgboost", n_estimators=30, early_stopping_rounds=5, n_jobs=1),
        )
        scored = score_pair_table(inference, model)
        required = [f"S1-{index}" for index in range(71, 77)]
        decisions = decide_queries(scored, required, DecisionPolicy(threshold=.5, top_k=1))
        candidates = {pair.s1_entity_id: (pair.candidate_entity_id,) for pair in scored}
        with tempfile.TemporaryDirectory() as raw:
            matching, candidate_path = export_submission(decisions, candidates, required, raw)
            self.assertEqual(len(matching.read_text().splitlines()), 7)
            self.assertTrue(candidate_path.is_file())


if __name__ == "__main__":
    unittest.main()
