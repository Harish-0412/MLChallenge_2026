import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.metrics import MetricInputError, f05_for_sets, macro_f05, score_f05  # noqa: E402


class MetricTests(unittest.TestCase):
    def test_official_edge_cases(self):
        self.assertEqual(f05_for_sets(set(), set()), 1.0)
        self.assertEqual(f05_for_sets(set(), {"S2-1"}), 0.0)
        self.assertEqual(f05_for_sets({"S2-1"}, set()), 0.0)
        self.assertEqual(f05_for_sets({"S2-1", "S3-1"}, {"S2-1", "S3-1"}), 1.0)
        self.assertAlmostEqual(f05_for_sets({"S2-1", "S3-1"}, {"S2-1", "S3-1", "S2-2"}), 5 / 7)
        self.assertAlmostEqual(f05_for_sets({"S2-1", "S3-1"}, {"S2-1"}), 5 / 6)

    def test_macro_includes_singletons(self):
        truth = {"S1-1": (), "S1-2": ("S2-1",)}
        pred = {"S1-1": (), "S1-2": ()}
        report = score_f05(truth, pred)
        self.assertEqual(report.macro_f05, 0.5)
        self.assertEqual(report.singleton_count, 1)

    def test_missing_query_is_rejected(self):
        with self.assertRaisesRegex(MetricInputError, "coverage mismatch"):
            macro_f05({"S1-1": (), "S1-2": ()}, {"S1-1": ()})

    def test_duplicate_prediction_is_rejected(self):
        with self.assertRaisesRegex(MetricInputError, "duplicates"):
            macro_f05({"S1-1": ("S2-1",)}, {"S1-1": ("S2-1", "S2-1")})

    def test_invalid_target_id_is_rejected(self):
        with self.assertRaisesRegex(MetricInputError, "invalid target"):
            macro_f05({"S1-1": ("S1-9",)}, {"S1-1": ()})


if __name__ == "__main__":
    unittest.main()

