"""End-to-end tests of scripts' build_manifest logic on a tiny synthetic project, including deliberate sabotage.

The point: reconciliation must REFUSE a wrong input, not just pass a right one.
"""
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import duckdb  # noqa: E402

from cleaning import manifest as m  # noqa: E402

S1 = [['S1-1', 'Acme Trading Pvt Ltd', '5 Main Rd, Pune, Maharashtra', 'India'],
      ['S1-2', 'Bison LLC', '610 Main Street, Thorntown, IN', 'US'],
      ['S1-3', 'Lille Club SAS', '72 Rue Royale, Lille', 'France']]
S2 = [['S2-1', 'ACME TRADING PVT LTD', '5 MAIN RD, PUNE', 'India'],
      ['S2-2', '"Bison LLC', '', 'US'],
      ['S2-3', 'Unmatched Co', 'Elsewhere', 'India']]
S3 = [['S3-1', 'आदित्य ट्रेडिंग', '5 Main Rd, Pune, MH', 'India'],
      ['S3-2', 'Bison  L.L.C.', '#610 Main Saint, Thorntown, Indiana', 'US'],
      ['S3-3', 'NA', '72 Rue Royale, Lille, Hauts-de-France', 'France']]
TRUTH = [['S1-1', 'S2-1,S3-1'], ['S1-2', 'S2-2,S3-2'], ['S1-3', 'S3-3']]
ROWS = {'train_source1': S1, 'train_source2': S2, 'train_source3': S3,
        'test_source1': S1, 'test_source2': S2, 'test_source3': S3}


def write_tsv(path: Path, rows, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header)
        writer.writerows(rows)


def make_project(root: Path, truth=TRUTH):
    """Tiny project: seven TSVs, Parquet copies, and an audit JSON whose numbers are written by hand."""
    dataset = root / m.DATASET_DIR
    files = []
    for name, relative in m.ALLOWLIST.items():
        path = dataset / relative
        if name == 'train_ground_truth':
            write_tsv(path, truth, m.TRUTH_COLUMNS)
        else:
            write_tsv(path, ROWS[name], m.SOURCE_COLUMNS)
        files.append({'file': str(Path(m.DATASET_DIR) / relative).replace('/', '\\'),
                      'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (dataset / '.DS_Store').write_bytes(b'metadata')
    interim = root / 'data' / 'interim'
    interim.mkdir(parents=True)
    con = duckdb.connect()
    for name in m.SOURCE_TABLES:
        scan = m.duckdb_csv_scan(dataset / m.ALLOWLIST[name], m.SOURCE_COLUMNS)
        con.execute(f"COPY (SELECT *, lower(business_name) AS name_key FROM {scan}) TO '{(interim / (name + '.parquet')).as_posix()}' (FORMAT PARQUET)")
    con.close()
    profiles = {}
    for name in m.SOURCE_TABLES:
        countries = {}
        for row in ROWS[name]:
            entry = countries.setdefault(row[3], [0, 0])
            entry[0] += 1
            entry[1] += row[2].strip() == ''
        profiles[name] = [{'country': c, 'rows': v[0], 'missing_address': v[1]} for c, v in sorted(countries.items())]
    audit = {'complete': True, 'files': files, 'profiles': profiles,
             'truth_integrity': {'rows': 3, 'positive_links': 5}}
    (root / 'reports' / 'eda').mkdir(parents=True)
    (root / 'reports' / 'eda' / 'full_audit.json').write_text(json.dumps(audit), encoding='utf-8')
    return dataset, interim


class ManifestBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        return m.build_manifest(self.root, workers=1, duckdb_memory='500MB', duckdb_threads=1, log=lambda _: None)

    def test_clean_project_reconciles_and_is_deterministic(self):
        make_project(self.root)
        manifest, _run = self.build()
        again, _ = self.build()
        self.assertEqual(m.dumps(manifest), m.dumps(again))
        self.assertTrue(all(manifest['reconciliation'].values()))
        self.assertEqual(manifest['totals'], {'source_rows': 18, 'label_rows': 3, 'positive_links': 5})
        self.assertEqual(manifest['excluded_files_never_read'], ['.DS_Store'])
        self.assertEqual(manifest['label_integrity']['links_to_source2'], 2)
        self.assertEqual(manifest['label_integrity']['links_to_source3'], 3)
        self.assertEqual(manifest['files']['test_source2']['python_parse']['rows_with_quote_char_in_value'], 1)

    def test_tampered_parquet_is_refused(self):
        _, interim = make_project(self.root)
        con = duckdb.connect()
        target = (interim / 'train_source2.parquet').as_posix()
        con.execute(f"COPY (SELECT entity_id, business_name, replace(business_address,'MAIN','MAIM') AS business_address, country, name_key "
                    f"FROM read_parquet('{target}')) TO '{target}.new' (FORMAT PARQUET)")
        con.close()
        Path(target + '.new').replace(target)
        with self.assertRaisesRegex(m.ManifestReconciliationError, 'Parquet copy differs'):
            self.build()

    def test_dropped_parquet_row_is_refused(self):
        _, interim = make_project(self.root)
        con = duckdb.connect()
        target = (interim / 'test_source3.parquet').as_posix()
        con.execute(f"COPY (SELECT * FROM read_parquet('{target}') WHERE entity_id<>'S3-3') TO '{target}.new' (FORMAT PARQUET)")
        con.close()
        Path(target + '.new').replace(target)
        with self.assertRaisesRegex(m.ManifestReconciliationError, 'Parquet copy differs'):
            self.build()

    def test_input_changed_since_audit_is_refused(self):
        dataset, _ = make_project(self.root)
        path = dataset / m.ALLOWLIST['test_source1']
        path.write_text(path.read_text(encoding='utf-8').replace('Acme', 'Acne'), encoding='utf-8', newline='')
        with self.assertRaisesRegex(m.ManifestReconciliationError, 'sha256/bytes differ'):
            self.build()

    def test_label_pointing_to_missing_target_is_refused(self):
        make_project(self.root, truth=[['S1-1', 'S2-1,S3-1'], ['S1-2', 'S2-2,S3-99'], ['S1-3', 'S3-3']])
        with self.assertRaisesRegex(m.ManifestReconciliationError, 'targets_missing_from_train_source2_source3'):
            self.build()

    def test_target_with_two_owners_is_refused(self):
        make_project(self.root, truth=[['S1-1', 'S2-1,S3-1'], ['S1-2', 'S2-1,S3-2'], ['S1-3', 'S3-3']])
        with self.assertRaisesRegex(m.ManifestReconciliationError, 'targets_with_multiple_source1_owners'):
            self.build()

    def test_missing_source1_label_row_is_refused(self):
        make_project(self.root, truth=[['S1-1', 'S2-1,S3-1'], ['S1-2', 'S2-2,S3-2']])
        with self.assertRaises(m.ManifestReconciliationError):
            self.build()

    def test_duplicate_id_is_flagged_as_structural_anomaly(self):
        dataset, _ = make_project(self.root)
        dup = ROWS['train_source3'] + [['S3-1', 'Dup', 'x', 'India']]
        write_tsv(dataset / m.ALLOWLIST['train_source3'], dup, m.SOURCE_COLUMNS)
        with self.assertRaises(m.ManifestReconciliationError):
            self.build()

    def test_stray_output_in_dataset_directory_aborts_before_reading(self):
        dataset, _ = make_project(self.root)
        (dataset / 'test' / 'matching_results.tsv').write_text('x', encoding='utf-8')
        with self.assertRaises(m.DatasetDiscoveryError):
            self.build()


if __name__ == '__main__':
    unittest.main()
