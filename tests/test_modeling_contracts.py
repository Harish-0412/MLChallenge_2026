import json
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.contracts import CandidateRecord, ContractError, ExperimentReport, table_from_candidates, validate_candidate_table  # noqa: E402
from modeling.pair_features import FEATURE_COLUMNS, assert_safe_feature_columns  # noqa: E402
from modeling.reproducibility import config_hash, load_json_config, set_global_seed, write_experiment_report  # noqa: E402


class ContractTests(unittest.TestCase):
    def test_candidate_round_trip(self):
        record = CandidateRecord("S1-1", "S2-2", "India", retrieval_channels=("exact_name",), retrieval_scores=(0.9,), retrieval_ranks=(1,))
        table = table_from_candidates([record])
        validate_candidate_table(table)
        self.assertEqual(table.num_rows, 1)

    def test_invalid_and_duplicate_candidates_fail(self):
        with self.assertRaises(ContractError):
            CandidateRecord("bad", "S2-2", "India").validate()
        row = CandidateRecord("S1-1", "S2-2", "India")
        with self.assertRaisesRegex(ContractError, "duplicate candidate"):
            validate_candidate_table(table_from_candidates([row, row]))

    def test_model_feature_allowlist_blocks_leakage(self):
        self.assertEqual(assert_safe_feature_columns(FEATURE_COLUMNS), FEATURE_COLUMNS)
        for forbidden in ("entity_id", "source", "split", "fold", "country", "truth_cardinality", "is_positive"):
            with self.assertRaises(ContractError, msg=forbidden):
                assert_safe_feature_columns((FEATURE_COLUMNS[0], forbidden))

    def test_config_hash_is_order_independent_and_seed_is_repeatable(self):
        self.assertEqual(config_hash({"a": 1, "b": 2}), config_hash({"b": 2, "a": 1}))
        import numpy as np
        set_global_seed(7)
        first = np.random.random(5)
        set_global_seed(7)
        self.assertTrue(np.array_equal(first, np.random.random(5)))

    def test_config_and_report_are_strict(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = root / "config.json"
            config.write_text('{"seed": 3}', encoding="utf-8")
            self.assertEqual(load_json_config(config), {"seed": 3})
            report = ExperimentReport("e1", "rev", "feat", "cand", "fold", 3, {})
            output = root / "report.json"
            write_experiment_report(report, output)
            self.assertEqual(json.loads(output.read_text())["experiment_id"], "e1")
            with self.assertRaises(FileExistsError):
                write_experiment_report(report, output)


if __name__ == "__main__":
    unittest.main()

