"""The verifier must be able to FAIL. Each test sabotages a finished synthetic table in one specific way and asserts that the intended check
(and, for the subtle ones, only that check) reports it. A clean table must pass everything."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

from cleaning import feature_verify, pipeline, record  # noqa: E402
from test_features_build import write_inputs  # noqa: E402

VERSION = 'feat_t'


class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='feat_verify_'))
        write_inputs(cls.tmp, rows_per_table=14)
        pipeline.build(cls.tmp, VERSION, workers=2, max_groups=99, check_inputs=False, log=lambda m: None)
        cls.fdir = cls.tmp / 'data' / 'features' / VERSION
        cls.pristine = cls.tmp / 'pristine'
        shutil.copytree(cls.fdir, cls.pristine)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(self.fdir)
        shutil.copytree(self.pristine, self.fdir)

    # ------------------------------------------------------------------ helpers
    def verify(self, determinism=False):
        return feature_verify.run_verification(self.tmp, VERSION, determinism=determinism, scans=False, threads=2, echo=False, recompute={'modulus': 1})

    def failed(self, report):
        return sorted(c['name'] for c in report.failed)

    def assertFails(self, report, *prefixes):
        names = self.failed(report)
        for prefix in prefixes:
            self.assertTrue(any(n.startswith(prefix) for n in names), f'{prefix!r} did not fail; failed: {names}')

    def target_file(self, split='train', source=1, country='India') -> Path:
        return next(self.fdir.glob(f'split={split}/source={source}/country={country}/*.parquet'))

    def rewrite(self, path: Path, mutate):
        """Rewrite one file with a mutated table and keep the build manifest honest, so only the check under test can notice."""
        table = mutate(pq.read_table(path))
        pq.write_table(table, path, compression='zstd')
        manifest_path = self.fdir / '_manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        rel = path.relative_to(self.fdir).as_posix()
        for part in manifest['partitions']:
            for f in part['files']:
                if f['path'] == rel:
                    f['rows'], f['bytes'] = pq.ParquetFile(path).metadata.num_rows, path.stat().st_size
            part['rows'] = sum(f['rows'] for f in part['files'])
            part['bytes'] = sum(f['bytes'] for f in part['files'])
        manifest['totals']['rows'] = sum(p['rows'] for p in manifest['partitions'])
        manifest['totals']['bytes'] = sum(p['bytes'] for p in manifest['partitions'])
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')

    @staticmethod
    def set_value(table: pa.Table, column: str, row: int, value) -> pa.Table:
        index = table.schema.get_field_index(column)
        values = table[column].to_pylist()
        values[row] = value
        return table.set_column(index, table.schema.field(index), pa.array(values, type=table.schema.field(index).type))

    # ------------------------------------------------------------------ tests
    def test_a_clean_table_passes_every_check(self):
        report = self.verify()
        self.assertEqual(self.failed(report), [], self.failed(report))
        self.assertGreater(len(report.checks), 100)

    def test_changed_raw_name_is_caught_against_the_input_copy(self):
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'business_name', 0, 'Tampered Name'))
        self.assertFails(self.verify(), 'B4 train_source1')

    def test_flipped_flag_is_caught_by_the_independent_regex(self):
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'name_has_control', 0, not t['name_has_control'][0].as_py()))
        self.assertFails(self.verify(), 'D7 name_has_control')

    def test_wrong_parse_confidence_is_caught_by_the_rule_restatement(self):
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'address_parse_conf', 0, 'low' if t['address_parse_conf'][0].as_py() != 'low' else 'high'))
        self.assertFails(self.verify(), 'D35')

    def test_wrong_segment_count_is_caught(self):
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'address_nsegments', 0, t['address_nsegments'][0].as_py() + 1))
        self.assertFails(self.verify(), 'D30')

    def test_a_dropped_row_is_caught_by_the_row_count(self):
        self.rewrite(self.target_file(), lambda t: t.slice(1))
        self.assertFails(self.verify(), 'B2 train_source1')

    def test_a_duplicated_row_is_caught(self):
        self.rewrite(self.target_file(), lambda t: pa.concat_tables([t, t.slice(0, 1)]))
        self.assertFails(self.verify(), 'B1 train_source1')

    def test_null_list_element_is_caught(self):
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'address_segments', 0, [None, 'x']))
        self.assertFails(self.verify(), 'C1')

    def test_stray_file_is_caught(self):
        (self.fdir / 'notes.txt').write_text('oops')
        self.assertFails(self.verify(), 'A6')

    def test_manifest_from_other_code_is_caught(self):
        path = self.fdir / '_manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['source_tree_sha256'] = '0' * 64
        path.write_text(json.dumps(manifest), encoding='utf-8')
        self.assertFails(self.verify(), 'A7')

    def test_partition_directory_that_disagrees_with_the_file_is_caught(self):
        source = self.target_file(country='US')
        wrong = source.parent.with_name('country=Bogus')
        shutil.move(str(source.parent), str(wrong))
        self.assertFails(self.verify(), 'C2', 'A2')

    def test_type_change_is_caught_by_the_schema_check(self):
        def widen(table):
            index = table.schema.get_field_index('name_ntokens')
            return table.set_column(index, pa.field('name_ntokens', pa.int32(), nullable=False), table['name_ntokens'].cast(pa.int32()))
        self.rewrite(self.target_file(), widen)
        self.assertFails(self.verify(), 'A3')

    def test_a_consistent_but_wrong_derived_value_is_caught_only_by_recomputation_and_the_rebuild(self):
        """name_translit 'zzz' satisfies every SQL invariant (ASCII, v1 fixed point, non-empty) but is not what the code produces."""
        self.rewrite(self.target_file(), lambda t: self.set_value(t, 'name_translit', 0, 'zzz'))
        report = self.verify(determinism=True)
        self.assertEqual([n for n in self.failed(report) if not n.startswith(('F1', 'G4'))], [], self.failed(report))
        self.assertFails(report, 'F1', 'G4')


if __name__ == '__main__':
    unittest.main()
