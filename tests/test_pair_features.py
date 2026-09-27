import json
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cleaning import record  # noqa: E402
from normalization import comparison_key  # noqa: E402
from modeling.contracts import CandidateRecord, table_from_candidates  # noqa: E402
from modeling.pair_features import FEATURE_COLUMNS, PAIR_SCHEMA, build_pair_table, feature_matrix  # noqa: E402


def make_feature(entity_id, name, address, country="India", split="train"):
    source = int(entity_id[1])
    return record.build_row(entity_id, name, address, country, comparison_key(name), comparison_key(address), split, source, "feat_test", "hyg_test")


class PairFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.feature_root = self.root / "features"
        self.feature_root.mkdir()
        rows = [
            make_feature("S1-1", "Acme Private Limited", "12 MG Road, Karnataka"),
            make_feature("S1-2", "Globex LLC", "90 Lake Road, Karnataka"),
            make_feature("S2-1", "ACME Pvt Ltd", "12 M G Rd Karnataka"),
            make_feature("S2-2", "Different Shop", "888 Other Street, Karnataka"),
            make_feature("S3-1", "Globex Limited Liability Company", "90 Lake Rd Karnataka"),
        ]
        pq.write_table(pa.Table.from_pylist([dict(zip(record.COLUMNS, row)) for row in rows], schema=record.SCHEMA), self.feature_root / "part.parquet")
        candidates = [
            CandidateRecord("S1-1", "S2-1", "India", retrieval_channels=("name", "address"), retrieval_scores=(1.0, .9), retrieval_ranks=(1, 1), candidate_block_size=2, query_candidate_count=2, is_positive=1),
            CandidateRecord("S1-1", "S2-2", "India", retrieval_channels=("fallback",), retrieval_scores=(.1,), retrieval_ranks=(2,), candidate_block_size=50, query_candidate_count=2, is_positive=0),
            CandidateRecord("S1-2", "S3-1", "India", retrieval_channels=("name",), retrieval_scores=(.8,), retrieval_ranks=(1,), candidate_block_size=3, query_candidate_count=1, is_positive=1),
        ]
        self.candidate_path = self.root / "candidates.parquet"
        pq.write_table(table_from_candidates(candidates), self.candidate_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_is_deterministic_and_manifested(self):
        first, second = self.root / "pairs1.parquet", self.root / "pairs2.parquet"
        m1 = build_pair_table(self.feature_root, self.candidate_path, first, batch_size=2, threads=1)
        m2 = build_pair_table(self.feature_root, self.candidate_path, second, batch_size=2, threads=1)
        t1, t2 = pq.read_table(first), pq.read_table(second)
        self.assertEqual(t1.schema, PAIR_SCHEMA)
        self.assertEqual(t1.to_pylist(), t2.to_pylist())
        self.assertEqual(m1["pair_rows"], 3)
        self.assertEqual(json.loads(first.with_suffix(".parquet.manifest.json").read_text())["pair_rows"], 3)

    def test_true_pair_has_stronger_features(self):
        output = self.root / "pairs.parquet"
        build_pair_table(self.feature_root, self.candidate_path, output, threads=1)
        rows = {(r["s1_entity_id"], r["candidate_entity_id"]): r for r in pq.read_table(output).to_pylist()}
        positive = rows[("S1-1", "S2-1")]
        negative = rows[("S1-1", "S2-2")]
        self.assertGreater(positive["name_core_ratio"], negative["name_core_ratio"])
        self.assertGreater(positive["address_canon_ratio"], negative["address_canon_ratio"])
        self.assertEqual(positive["retrieval_channel_count"], 2.0)

    def test_matrix_contains_only_allowlisted_features(self):
        output = self.root / "pairs.parquet"
        build_pair_table(self.feature_root, self.candidate_path, output, threads=1)
        matrix = feature_matrix(pq.read_table(output))
        self.assertEqual(matrix.shape, (3, len(FEATURE_COLUMNS)))
        self.assertEqual(str(matrix.dtype), "float32")

    def test_refuses_overwrite(self):
        output = self.root / "pairs.parquet"
        build_pair_table(self.feature_root, self.candidate_path, output, threads=1)
        with self.assertRaises(FileExistsError):
            build_pair_table(self.feature_root, self.candidate_path, output, threads=1)


if __name__ == "__main__":
    unittest.main()

