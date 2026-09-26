"""The scanner is the instrument behind the Phase 2 acceptance numbers, so it is tested against hand-counted rows."""
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import hygiene_scan as scan  # noqa: E402
from cleaning.lexicons import legal_dotted  # noqa: E402
from normalization import comparison_key as v1  # noqa: E402


def row(eid, name, address, country, name_key=None, address_key=None):
    return (eid, name, address, country, v1(name) if name_key is None else name_key,
            v1(address) if address_key is None else address_key)


ROWS = [
    row('S1-1', 'Bison  L.L.C.', '5 Main St', 'US'),
    row('S2-1', 'ಕನ್‌ಸ್', 'X\x1aY', 'India'),
    row('S3-1', 'NA', '', 'France'),
    row('S1-2', 'École N° 5', 'Rue de l’Eglise', 'France'),
    row('S1-3', 'Plain Corp', '5 Main Rd', 'US', address_key='WRONG'),   # deliberately wrong stored v1 address key
    row('S3-2', 'Acme Ltd', '5 Main Rd', 'US'),
]


def total(result, metric):
    return sum(v for (t, c, m), v in result['counts'].items() if m == metric)


class ScanRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = scan.scan_rows('t', ROWS, legal_dotted())

    def test_row_counts_by_country(self):
        got = {c: v for (t, c, m), v in self.result['counts'].items() if m == 'rows'}
        self.assertEqual(got, {'US': 3, 'India': 1, 'France': 2})

    def test_repair_counts(self):
        expected = {'repair:name:dotted': 1, 'repair:name:ws': 1, 'repair:name:joiners': 1, 'repair:name:punct': 1,
                    'repair:address:controls': 1, 'repair:address:punct': 1}
        for metric, n in expected.items():
            self.assertEqual(total(self.result, metric), n, metric)
        self.assertEqual(total(self.result, 'repair:name:controls'), 0)
        self.assertEqual(total(self.result, 'repair:address:ws'), 0)

    def test_flag_counts(self):
        expected = {'flag:name_multispace': 1, 'flag:name_has_format': 1, 'flag:any_format': 1, 'flag:address_has_control': 1,
                    'flag:address_mojibake': 1, 'flag:any_control': 1, 'flag:address_missing': 1, 'flag:name_has_control': 0,
                    'flag:address_multispace': 0}
        for metric, n in expected.items():
            self.assertEqual(total(self.result, metric), n, metric)

    def test_difference_from_v1_is_counted_per_view(self):
        expected = {'differs_v1:name_hyg': 3, 'differs_v1:name_latin_accent_key': 1, 'differs_v1:name_joiner_key': 1,
                    'differs_v1:name_compat_key': 0, 'differs_v1:name_apos_join_key': 3, 'differs_v1:address_clean': 1}
        for metric, n in expected.items():
            self.assertEqual(total(self.result, metric), n, metric)

    def test_v1_parity_failure_is_detected_and_located(self):
        self.assertEqual(total(self.result, 'v1_parity_fail:address'), 1)
        self.assertEqual(total(self.result, 'v1_parity_fail:name'), 0)
        table, eid, field, raw, stored, computed = self.result['parity_failures'][0]
        self.assertEqual((table, eid, field, stored, computed), ('t', 'S1-3', 'address', 'WRONG', '5 main rd'))

    def test_no_empties_losses_or_non_idempotence(self):
        for metric in ['empty:name_hyg', 'empty:name_latin_accent_key', 'addr_new_empty', 'mn_lost:name_hyg', 'mn_lost:address_clean',
                       'not_idempotent:name_hyg', 'not_idempotent:address_clean', 'not_idempotent:name_latin_accent_key']:
            self.assertEqual(total(self.result, metric), 0, metric)

    def test_dotted_census_and_flagged_rows_and_examples(self):
        self.assertEqual(dict(self.result['dotted_census']), {'llc': 1})
        self.assertEqual([f[1] for f in self.result['flagged']], ['S2-1'])
        self.assertEqual(self.result['examples'][('name', 'dotted')][0][:2], ('S1-1', 'Bison  L.L.C.'))

    def test_mn_lost_detects_a_lost_mark_and_a_lost_digit(self):
        self.assertTrue(scan.mn_lost('आदित्य', 'आदित य'))       # a vowel sign (Mc) lost
        self.assertTrue(scan.mn_lost('Plot 148', 'plot 14'))     # a digit lost
        self.assertFalse(scan.mn_lost('École 5', 'école 5'))
        self.assertFalse(scan.mn_lost('आदित्य', 'आदित्य'))

    def test_merge_adds_counts_and_keeps_examples_sorted_and_bounded(self):
        a = scan.scan_rows('t', ROWS[:3], legal_dotted())
        b = scan.scan_rows('t', ROWS[3:], legal_dotted())
        merged = scan.merge([a, b])
        whole = scan.scan_rows('t', ROWS, legal_dotted())
        self.assertEqual(merged['counts'], whole['counts'])
        self.assertEqual(merged['dotted_census'], whole['dotted_census'])
        self.assertLessEqual(len(merged['examples'][('name', 'ws')]), scan.EXAMPLES_PER_CODE)


class ScanParquetTests(unittest.TestCase):
    def test_row_group_task_reads_parquet_and_matches_in_memory_scan(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.parquet'
            columns = ['entity_id', 'business_name', 'business_address', 'country', 'name_key', 'address_key']
            table = pa.table({c: [r[i] for r in ROWS] for i, c in enumerate(columns)})
            pq.write_table(table, path, row_group_size=4)          # 6 rows -> row groups of 4 and 2
            groups = pq.ParquetFile(path).num_row_groups
            self.assertEqual(groups, 2)
            merged = scan.merge(scan.scan_row_group(('t', str(path), g)) for g in range(groups))
        whole = scan.scan_rows('t', ROWS, legal_dotted())
        self.assertEqual(merged['counts'], whole['counts'])
        self.assertEqual(merged['rows'], 6)


if __name__ == '__main__':
    unittest.main()
