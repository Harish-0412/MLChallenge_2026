import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import duckdb  # noqa: E402

from cleaning import manifest as m  # noqa: E402

MANIFEST_PATH = ROOT / 'manifests' / 'input_manifest_v1.json'


def write_tsv(path: Path, rows, header=None):
    """Written with the csv module and default minimal quoting: the same convention the real files follow."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
    return path


TRICKY = [
    ['S2-001', 'NA', '', 'France'],                                        # literal NA, empty address
    ['S2-002', '"ehpad Club SAS', '4 Rue Daurat, Nantes', 'France'],       # value that STARTS with a double quote
    ['S2-003', 'Federation du "ehpad', 'Bordeaux, "C" Road', 'France'],    # quotes inside values
    ['S2-004', 'आदित्य ट्रेडिंग प्रा. लि.', 'OFFICE NO J 5-105, महाराष्ट्र', 'India'],
    ['S2-005', 'Black Limited  Pharmacy', "Plot Â\x80\x93 148, Mira Nagar", 'India'],  # double space, mojibake dash
    ['S2-006', '  padded  ', '   ', 'US'],                                  # whitespace-only address
]


class DiscoveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / m.DATASET_DIR
        for relative in m.ALLOWLIST.values():
            write_tsv(self.dataset / relative, [])

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowlisted_file_is_accepted(self):
        path = self.dataset / m.ALLOWLIST['train_source1']
        self.assertEqual(m.discovery_guard(path, self.dataset), path.resolve())

    def test_allowlist_rejects_metadata(self):
        for bad in ['train/._train_source1.tsv', '.DS_Store', '__MACOSX/train/train_source1.tsv']:
            path = self.dataset / bad
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'x')
            with self.assertRaises(m.DatasetDiscoveryError, msg=bad):
                m.discovery_guard(path, self.dataset)

    def test_rejects_outputs_reports_and_unlisted_files(self):
        for bad in ['reports/eda/positive_pair_sample_s2.tsv', 'output/matching_results.tsv', 'train/extra_source.tsv']:
            path = self.dataset / bad
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'x')
            with self.assertRaises(m.DatasetDiscoveryError, msg=bad):
                m.discovery_guard(path, self.dataset)

    def test_rejects_path_outside_dataset_directory(self):
        outside = self.root / 'data' / 'interim' / 'train_source1.tsv'
        outside.parent.mkdir(parents=True)
        outside.write_bytes(b'x')
        with self.assertRaises(m.DatasetDiscoveryError):
            m.discovery_guard(outside, self.dataset)

    def test_resolve_lists_metadata_but_never_returns_it(self):
        (self.dataset / '.DS_Store').write_bytes(b'x')
        (self.dataset / 'train' / '._train_source1.tsv').write_bytes(b'x')
        paths, excluded = m.resolve_allowlist(self.root)
        self.assertEqual(sorted(paths), sorted(m.ALLOWLIST))
        self.assertEqual(excluded, ['.DS_Store', 'train/._train_source1.tsv'])

    def test_resolve_fails_on_stray_data_file(self):
        (self.dataset / 'test' / 'candidate_pairs.tsv').write_bytes(b'x')
        with self.assertRaises(m.DatasetDiscoveryError):
            m.resolve_allowlist(self.root)

    def test_resolve_fails_when_an_allowlisted_file_is_missing(self):
        (self.dataset / m.ALLOWLIST['test_source3']).unlink()
        with self.assertRaises(m.DatasetDiscoveryError):
            m.resolve_allowlist(self.root)


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_python_and_duckdb_agree_on_tricky_fixture(self):
        path = write_tsv(self.dir / 't.tsv', TRICKY, m.SOURCE_COLUMNS)
        python = m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 2)
        con = duckdb.connect()
        rows = con.execute(f'SELECT * FROM {m.duckdb_csv_scan(path, m.SOURCE_COLUMNS)} ORDER BY entity_id').fetchall()
        duck = m.duckdb_profile(con, m.duckdb_csv_scan(path, m.SOURCE_COLUMNS))
        con.close()
        self.assertEqual(rows, [tuple(r) for r in TRICKY])   # values survive parsing unchanged
        for key in ['rows', 'distinct_ids', 'name_codepoints', 'address_codepoints', 'per_country']:
            self.assertEqual(python[key], duck[key], key)
        self.assertEqual(python['empty_address_after_strip'], duck['empty_address_after_trim'])
        self.assertEqual(python['rows'], 6)
        self.assertEqual(python['empty_address_after_strip'], 2)
        self.assertEqual(python['lines_with_double_quote'], 2)
        self.assertEqual(python['physical_lines'], 7)
        self.assertEqual(python['id_prefix_violations'], 0)

    def test_quote_aware_parse_differs_from_naive_split(self):
        """The reason parsing must be quote-aware: 134 test-S1 rows start with a double quote."""
        path = write_tsv(self.dir / 't.tsv', TRICKY, m.SOURCE_COLUMNS)
        line = path.read_text(encoding='utf-8').split('\n')[2]
        naive = line.split('\t')
        parsed = next(r for r in csv.reader([line], delimiter='\t') if r)
        self.assertEqual(parsed[1], '"ehpad Club SAS')
        self.assertNotEqual(naive[1], parsed[1])

    def test_literal_na_is_text_not_null(self):
        path = write_tsv(self.dir / 't.tsv', TRICKY, m.SOURCE_COLUMNS)
        con = duckdb.connect()
        value = con.execute(f"SELECT business_name FROM {m.duckdb_csv_scan(path, m.SOURCE_COLUMNS)} WHERE entity_id='S2-001'").fetchone()[0]
        con.close()
        self.assertEqual(value, 'NA')

    def test_duckdb_scan_identical_to_audit_scan(self):
        from audit_dataset import csv_scan
        p = Path('x.tsv')
        self.assertEqual(m.duckdb_csv_scan(p, m.SOURCE_COLUMNS), csv_scan(p, m.SOURCE_COLUMNS))
        self.assertEqual(m.duckdb_csv_scan(p, m.TRUTH_COLUMNS), csv_scan(p, m.TRUTH_COLUMNS))

    def test_wrong_header_rejected_with_location(self):
        path = write_tsv(self.dir / 't.tsv', [['S1-1', 'A', 'B', 'US']], ['id', 'name', 'address', 'country'])
        with self.assertRaises(m.MalformedInputError) as caught:
            m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)
        self.assertEqual(caught.exception.line, 1)

    def test_missing_column_rejected_with_line_number(self):
        path = self.dir / 't.tsv'
        path.write_text('\t'.join(m.SOURCE_COLUMNS) + '\nS1-1\tAcme\tNY\tUS\nS1-2\tAcme\tUS\n', encoding='utf-8')
        with self.assertRaises(m.MalformedInputError) as caught:
            m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)
        self.assertEqual(caught.exception.line, 3)

    def test_invalid_utf8_rejected(self):
        path = self.dir / 't.tsv'
        path.write_bytes('\t'.join(m.SOURCE_COLUMNS).encode() + b'\nS1-1\tAcme \xff\xfe\tNY\tUS\n')
        with self.assertRaises(m.MalformedInputError):
            m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)

    def test_unterminated_quote_fails_loudly(self):
        path = self.dir / 't.tsv'
        path.write_text('\t'.join(m.SOURCE_COLUMNS) + '\nS1-1\t"Acme\tNY\tUS\nS1-2\tB\tNY\tUS\n', encoding='utf-8')
        with self.assertRaises(m.MalformedInputError):
            m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)

    def test_prefix_duplicates_and_format_are_counted(self):
        path = write_tsv(self.dir / 't.tsv', [['S1-1', 'A', 'x', 'US'], ['S1-1', 'B', 'y', 'US'], ['S2-3', 'C', 'z', 'US'], ['bad', 'D', 'w', 'US']],
                         m.SOURCE_COLUMNS)
        result = m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)
        self.assertEqual((result['rows'], result['distinct_ids']), (4, 3))
        self.assertEqual(result['id_prefix_violations'], 2)
        self.assertEqual(result['id_format_violations'], 1)

    def test_multiline_quoted_field_is_visible_in_physical_lines(self):
        path = self.dir / 't.tsv'
        path.write_text('\t'.join(m.SOURCE_COLUMNS) + '\nS1-1\t"line1\nline2"\tNY\tUS\n', encoding='utf-8')
        result = m.profile_tsv(path, m.SOURCE_COLUMNS, 'source', 1)
        self.assertEqual(result['rows'], 1)
        self.assertEqual(result['physical_lines'], 3)   # rows + 1 would be 2: the manifest treats this as an anomaly

    def test_truth_profile(self):
        path = write_tsv(self.dir / 'g.tsv', [['S1-1', 'S2-1,S3-1'], ['S1-2', ''], ['S1-3', 'S2-2,S2-2'], ['S1-4', 'S9-1']], m.TRUTH_COLUMNS)
        result = m.profile_tsv(path, m.TRUTH_COLUMNS, 'truth')
        self.assertEqual(result['rows'], 4)
        self.assertEqual(result['rows_with_no_matches'], 1)
        self.assertEqual(result['positive_links'], 5)
        self.assertEqual(result['rows_with_duplicate_ids_in_list'], 1)
        self.assertEqual(result['target_id_format_violations'], 1)
        self.assertEqual(result['match_count_distribution'], {'0': 1, '1': 1, '2': 2})

    def test_dumps_is_deterministic(self):
        first = m.dumps({'b': 1, 'a': {'d': 2, 'c': [3, 'é']}})
        second = m.dumps({'a': {'c': [3, 'é'], 'd': 2}, 'b': 1})
        self.assertEqual(first, second)


@unittest.skipUnless(MANIFEST_PATH.exists(), 'run scripts/build_manifest.py first')
class RecordedManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
        cls.audit = json.loads((ROOT / 'reports' / 'eda' / 'full_audit.json').read_text(encoding='utf-8'))

    def test_manifest_row_counts_match_audit(self):
        for name in m.SOURCE_TABLES:
            audit_total = sum(r['rows'] for r in self.audit['profiles'][name])
            self.assertEqual(self.manifest['files'][name]['python_parse']['rows'], audit_total, name)
            self.assertEqual(self.manifest['files'][name]['parquet_copy']['rows'], audit_total, name)
        self.assertEqual(self.manifest['totals']['source_rows'], 24_229_173)
        self.assertEqual(self.manifest['totals']['label_rows'], 2_206_821)
        self.assertEqual(self.manifest['totals']['positive_links'], 7_638_365)

    def test_no_id_disappears_between_raw_and_derived(self):
        for name in m.SOURCE_TABLES:
            f = self.manifest['files'][name]
            self.assertEqual(f['python_parse']['distinct_ids'], f['python_parse']['rows'], name)
            self.assertEqual(f['duckdb_raw_parse']['content_hash_sum'], f['parquet_copy']['content_hash_sum'], name)
            self.assertEqual(f['duckdb_raw_parse']['distinct_ids'], f['parquet_copy']['distinct_ids'], name)

    def test_hashes_equal_audit(self):
        audit = {Path(i['file'].replace('\\', '/')).as_posix(): i for i in self.audit['files']}
        for name, f in self.manifest['files'].items():
            self.assertEqual(f['sha256'], audit[f['path']]['sha256'], name)

    def test_all_reconciliation_checks_passed(self):
        self.assertTrue(all(self.manifest['reconciliation'].values()), self.manifest['reconciliation'])

    def test_label_integrity_is_clean(self):
        labels = self.manifest['label_integrity']
        for key in ['source1_ids_missing_from_truth', 'truth_ids_unknown_in_train_source1', 'duplicate_pairs',
                    'targets_with_multiple_source1_owners', 'targets_missing_from_train_source2_source3', 'links_with_country_mismatch']:
            self.assertEqual(labels[key], 0, key)
        self.assertEqual(labels['links_to_source2'], 3_693_619)
        self.assertEqual(labels['links_to_source3'], 3_944_746)

    def test_metadata_is_excluded_and_recorded(self):
        self.assertIn('.DS_Store', self.manifest['excluded_files_never_read'])
        self.assertEqual(sorted(self.manifest['allowlist']), sorted(m.ALLOWLIST))

    def test_sidecar_hash_matches_manifest_file(self):
        sidecar = (ROOT / 'manifests' / 'input_manifest_v1.sha256').read_text(encoding='utf-8').split()[0]
        self.assertEqual(sidecar, m.sha256_file(MANIFEST_PATH))

    def test_inputs_on_disk_still_match_manifest(self):
        m.assert_inputs_match_manifest(ROOT, MANIFEST_PATH)


if __name__ == '__main__':
    unittest.main()
