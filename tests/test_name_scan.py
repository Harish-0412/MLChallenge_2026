"""The name scanner is the instrument behind the Phase 3 acceptance numbers, so it is tested on hand-counted rows."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import name_scan as scan  # noqa: E402
from normalization import comparison_key as v1  # noqa: E402

RAW = [
    ('S1-1', 'Sun Industries L.L.P.', 'India'),
    ('S1-2', 'Dr Modern Enterprises LLP', 'India'),
    ('S1-3', 'NA', 'US'),
    ('S1-4', 'globalclassicsouthwest.com', 'US'),
    ('S1-5', 'Novisynxylo d/b/a Sullivan Regional Pegasus LLC', 'US'),
    ('S1-6', 'LLC', 'US'),
    ('S1-7', '-- Rose Trading Privtate Limited', 'India'),
    ('S1-8', 'M/s Foo Traders Pvt Ltd', 'India'),
    ('S1-9', 'Foo Bar', 'US'),
]
ROWS = [(e, n, '5 Main Rd, Pune', c, v1(n)) for e, n, c in RAW]


def total(counts, metric):
    return sum(v for (t, c, m), v in counts.items() if m == metric)


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counts, cls.examples, cls.keys = scan.scan_rows('t', ROWS, collect_keys=True)

    def test_hand_counted_metrics(self):
        # legal forms present: S1-1 LLP, S1-2 LLP, S1-5 LLC, S1-6 LLC, S1-7 LTD, S1-8 PVT+LTD  -> 6 rows
        self.assertEqual(total(self.counts, 'rows'), 9)
        self.assertEqual(total(self.counts, 'has_legal_form'), 6)
        self.assertEqual(total(self.counts, 'legal_code:LLP'), 2)
        self.assertEqual(total(self.counts, 'legal_code:LLC'), 2)
        self.assertEqual(total(self.counts, 'legal_code:LTD'), 2)
        self.assertEqual(total(self.counts, 'legal_code:PVT'), 1)
        self.assertEqual(total(self.counts, 'legal_pos:suffix'), 6)
        self.assertEqual(total(self.counts, 'fallback'), 1)                   # S1-6 'LLC'
        self.assertEqual(total(self.counts, 'placeholder'), 1)                # S1-3
        self.assertEqual(total(self.counts, 'domain_like'), 1)                # S1-4
        self.assertEqual(total(self.counts, 'noise_prefix'), 1)               # S1-7
        self.assertEqual(total(self.counts, 'noise_prefix:--'), 1)
        self.assertEqual(total(self.counts, 'alias:dba'), 1)                  # S1-5
        self.assertEqual(total(self.counts, 'leading:dr'), 1)                 # S1-2
        self.assertEqual(total(self.counts, 'leading:m/s'), 1)                # S1-8
        self.assertEqual(total(self.counts, 'ms_pattern_rows'), 1)
        self.assertEqual(total(self.counts, 'bracket_text'), 0)

    def test_no_violations_on_clean_rows(self):
        for metric in ['violation:core_empty', 'violation:not_subsequence', 'violation:not_idempotent', 'violation:ntokens',
                       'violation:set_or_compact', 'violation:unknown_code', 'violation:pos_mismatch', 'violation:fallback_mismatch']:
            self.assertEqual(total(self.counts, metric), 0, metric)

    def test_core_differs_from_v1_key_where_expected(self):
        # cores equal to the v1 key: 'NA' (S1-3), 'LLC' (S1-6, all-legal fallback) and 'Foo Bar' (S1-9) -> the other 6 differ
        self.assertEqual(total(self.counts, 'core_differs_v1'), 6)

    def test_collected_keys_align_with_rows(self):
        self.assertEqual({len(v) for v in self.keys.values()}, {9})
        self.assertEqual(self.keys['name_core'][0], 'sun industries')
        self.assertEqual(self.keys['name_core'][1], 'modern enterprises')
        self.assertEqual(self.keys['name_core_compact'][3], 'globalclassicsouthwest')
        self.assertEqual(self.keys['name_key'][0], 'sun industries l l p')     # the v1 key is carried unchanged
        self.assertEqual(self.keys['name_hyg'][0], 'sun industries llp')

    def test_a_scanner_that_sees_a_broken_invariant_reports_it(self):
        from unittest import mock
        real = scan.N.build_name_features

        def broken(raw, country, cleaned=None):
            out = real(raw, country, cleaned)
            out['name_core'] = ''            # simulate a bug that empties the core
            return out

        with mock.patch.object(scan.N, 'build_name_features', broken):
            counts, _e, _k = scan.scan_rows('t', ROWS)
        self.assertGreater(total(counts, 'violation:core_empty'), 0)
        self.assertGreater(total(counts, 'violation:ntokens'), 0)

    def test_row_group_task_writes_keys_and_matches_in_memory_scan(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'train_source1.parquet'
            cols = ['entity_id', 'business_name', 'business_address', 'country', 'name_key']
            pq.write_table(pa.table({c: [r[i] for r in ROWS] for i, c in enumerate(cols)}), path, row_group_size=5)
            groups = pq.ParquetFile(path).num_row_groups
            self.assertEqual(groups, 2)
            scratch = Path(folder) / 'scratch'
            merged = scan.merge(scan.scan_row_group(('train_source1', str(path), g, str(scratch))) for g in range(groups))
            written = sorted(scratch.glob('*.parquet'))
            keys = pq.read_table(written[0]).to_pydict()
        self.assertEqual(len(written), 2)
        in_memory, _e, _k = scan.scan_rows('train_source1', ROWS)
        self.assertEqual(merged['counts'], in_memory)
        self.assertEqual(list(keys), scan.KEY_COLUMNS)


if __name__ == '__main__':
    unittest.main()
