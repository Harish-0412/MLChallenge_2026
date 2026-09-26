"""Phase 6: build pipeline on a small synthetic input (six tiny Parquet tables with several row groups each).

The real 24M-row build is verified by scripts/verify_features.py; these tests pin the pipeline's behaviour: partitioning (incl. an
awkward country label), raw pass-through, determinism across worker count and flush size, refuse-to-overwrite, failure cleanliness, and
the source hash that ties a table to the code that made it.
"""
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import FEATURE_VERSION, HYGIENE_VERSION, pipeline, record  # noqa: E402
from cleaning.manifest import SOURCE_TABLES  # noqa: E402
from normalization import comparison_key  # noqa: E402

ROW_POOL = [
    ('India', 'Sharma Traders Pvt. Ltd.', 'H.NO:003-2-146, ROAD NO, 6 Shathavahana Nagar, Hyderabad, Telangana'),
    ('India', 'श्री गणेश ट्रेडर्स', ''),
    ('US', 'ACME Widgets LLC', '140 TELULAH AVENUE, PO BOX 2989, CITY OF APPLETON, WI'),
    ('US', 'Tab\x07le Inc', '022 CHAMPLAIN AVE, LEWISTON, ME'),
    ('France', 'Société Dupont SARL', 'N° 57 AVENUE DU MARÉCHAL DE LATTRE DE TASSIGNY, LA BAULE-ESCOUBLAC, Pays de la Loire'),
    ('France', 'Caf\x80 Bar', '   '),
    ('India', 'Plot No, 93 Traders', 'Plot No, 93, Sector 5, Pune, Maharashtra'),
]


def write_inputs(root: Path, odd_country: bool = False, bad_id: bool = False, rows_per_table: int = 14) -> None:
    interim = root / 'data' / 'interim'
    interim.mkdir(parents=True)
    for table in SOURCE_TABLES:
        source = table[-1]
        cols = {'entity_id': [], 'business_name': [], 'business_address': [], 'country': [], 'name_key': [], 'address_key': []}
        for n in range(rows_per_table):
            country, name, address = ROW_POOL[n % len(ROW_POOL)]
            if odd_country and n == 3:
                country = "Côte d'Ivoire / East & West"
            entity_id = f'S{source}-{1000 + n}' if not (bad_id and n == 5 and table == 'test_source3') else 'BADID'
            for key, value in zip(cols, (entity_id, name, address, country, comparison_key(name), comparison_key(address))):
                cols[key].append(value)
        pq.write_table(pa.table(cols), interim / f'{table}.parquet', row_group_size=4)


def file_hashes(base: Path) -> dict:
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob('*.parquet'))}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='feat_test_'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, version='feat_t', **kw):
        kw.setdefault('workers', 2)
        return pipeline.build(self.tmp, version, check_inputs=False, log=lambda m: None, **kw)

    def test_counts_partitions_and_raw_passthrough(self):
        write_inputs(self.tmp, odd_country=True)
        result = self.build()
        fdir = self.tmp / 'data' / 'features' / 'feat_t'
        self.assertEqual(result['manifest']['totals']['rows'], 14 * 6)
        self.assertFalse(fdir.with_name('feat_t.tmp').exists())
        seen = {}
        for path in fdir.rglob('*.parquet'):
            data = pq.read_table(path)
            self.assertTrue(data.schema.equals(record.SCHEMA, check_metadata=False), path)
            rel = path.relative_to(fdir).parts
            self.assertEqual(rel[0], f"split={data['split'][0].as_py()}")
            self.assertEqual(rel[1], f"source={data['source'][0].as_py()}")
            self.assertEqual(rel[2], 'country=' + quote(data['country'][0].as_py(), safe=''))
            for row in data.to_pylist():
                seen[row['entity_id'], row['split']] = row
        self.assertEqual(len(seen), 14 * 6)
        for table_name in SOURCE_TABLES:
            split = table_name.split('_source')[0]
            for raw in pq.read_table(self.tmp / 'data' / 'interim' / f'{table_name}.parquet').to_pylist():
                got = seen[raw['entity_id'], split]
                for key in ('business_name', 'business_address', 'country', 'name_key', 'address_key'):
                    self.assertEqual(got[key], raw[key], key)
                self.assertEqual(got['id_num'], int(raw['entity_id'].split('-')[1]))
                self.assertEqual((got['feature_version'], got['hygiene_version']), ('feat_t', HYGIENE_VERSION))
        awkward = "Côte d'Ivoire / East & West"
        self.assertTrue(any(p.name == 'country=' + quote(awkward, safe='') for p in fdir.rglob('country=*')))

    def test_specific_rows_carry_the_documented_features(self):
        write_inputs(self.tmp)
        self.build()
        rows = {}
        for path in (self.tmp / 'data' / 'features' / 'feat_t').rglob('*.parquet'):
            for row in pq.read_table(path).to_pylist():
                rows[row['entity_id'], row['split']] = row
        blank = next(r for r in rows.values() if r['business_name'] == 'Caf\x80 Bar')
        self.assertTrue(blank['address_missing'] and blank['name_mojibake'])
        self.assertEqual((blank['address_parse_conf'], blank['address_segments'], blank['address_canon']), ('missing', [], ''))
        po = next(r for r in rows.values() if r['business_name'] == 'ACME Widgets LLC')
        self.assertEqual((po['legal_form'], po['name_core'], po['address_extras'], po['address_state_canon']), ('LLC', 'acme widgets', 'po box 2989', 'wisconsin'))
        control = next(r for r in rows.values() if r['business_name'].startswith('Tab'))
        self.assertTrue(control['name_has_control'])
        plot = next(r for r in rows.values() if r['business_name'].startswith('Plot No'))
        self.assertEqual(plot['address_segments'], ['plot', '93', 'sector 5', 'pune', 'maharashtra'])

    def test_refuses_to_overwrite_a_finished_version(self):
        write_inputs(self.tmp)
        self.build()
        before = file_hashes(self.tmp / 'data' / 'features' / 'feat_t')
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(file_hashes(self.tmp / 'data' / 'features' / 'feat_t'), before)

    def test_a_failing_build_leaves_no_finished_version_and_the_next_build_recovers(self):
        write_inputs(self.tmp, bad_id=True)
        with self.assertRaises(Exception):
            self.build()
        self.assertFalse((self.tmp / 'data' / 'features' / 'feat_t').exists(), 'a failed build must not look finished')
        shutil.rmtree(self.tmp / 'data' / 'interim')
        write_inputs(self.tmp)
        self.build()          # a leftover .tmp directory from the failed run is cleaned up, not merged
        self.assertTrue((self.tmp / 'data' / 'features' / 'feat_t' / '_manifest.json').exists())
        self.assertEqual(sum(pq.ParquetFile(p).metadata.num_rows for p in (self.tmp / 'data' / 'features' / 'feat_t').rglob('*.parquet')), 14 * 6)

    def test_deterministic_across_worker_count_and_flush_size(self):
        write_inputs(self.tmp, odd_country=True)
        a = self.build('feat_t', workers=1, out_base=self.tmp / 'a')
        b = self.build('feat_t', workers=3, out_base=self.tmp / 'b')
        self.assertEqual(file_hashes(self.tmp / 'a' / 'feat_t'), file_hashes(self.tmp / 'b' / 'feat_t'))
        self.assertEqual(a['manifest'], b['manifest'])
        c = self.build('feat_t', workers=2, flush_rows=3, out_base=self.tmp / 'c')
        for rel in file_hashes(self.tmp / 'a' / 'feat_t'):
            self.assertTrue(pq.read_table(self.tmp / 'a' / 'feat_t' / rel).equals(pq.read_table(self.tmp / 'c' / 'feat_t' / rel)), rel)
        self.assertNotEqual(file_hashes(self.tmp / 'a' / 'feat_t'), file_hashes(self.tmp / 'c' / 'feat_t'), 'flush=3 must change the row-group layout')
        self.assertEqual(c['manifest']['totals']['rows'], a['manifest']['totals']['rows'])

    def test_max_groups_builds_a_sample_and_the_manifest_says_so(self):
        write_inputs(self.tmp)
        result = self.build(max_groups=1)
        self.assertTrue(result['manifest']['sample_build'])
        self.assertEqual(result['manifest']['totals']['rows'], 4 * 6)


class SourceHashTests(unittest.TestCase):
    def test_hash_covers_features_code_and_lexicons_but_not_verification_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'src' / 'cleaning'
            (base / 'lexicon_data').mkdir(parents=True)
            (base / 'names.py').write_text('x = 1\n')
            (base / 'lexicon_data' / 'a.tsv').write_text('a\tb\n')
            (base / 'feature_verify.py').write_text('check = 1\n')
            first = pipeline.source_tree_hash(Path(tmp))
            (base / 'feature_verify.py').write_text('check = 2\n')
            self.assertEqual(pipeline.source_tree_hash(Path(tmp)), first, 'verification code must not change the table hash')
            (base / 'names.py').write_text('x = 2\n')
            second = pipeline.source_tree_hash(Path(tmp))
            self.assertNotEqual(second, first)
            (base / 'lexicon_data' / 'a.tsv').write_text('a\tc\n')
            self.assertNotEqual(pipeline.source_tree_hash(Path(tmp)), second)

    def test_real_tree_hash_is_stable_and_hex(self):
        one, two = pipeline.source_tree_hash(ROOT), pipeline.source_tree_hash(ROOT)
        self.assertEqual(one, two)
        self.assertRegex(one, r'^[0-9a-f]{64}$')


class SchemaTests(unittest.TestCase):
    def test_schema_matches_the_column_list_and_types(self):
        self.assertEqual(record.SCHEMA.names, list(record.COLUMNS))
        self.assertEqual(len(record.COLUMNS), 69)
        self.assertTrue(all(not f.nullable for f in record.SCHEMA))
        self.assertEqual(str(record.SCHEMA.field('source').type), 'int8')
        self.assertEqual(str(record.SCHEMA.field('address_segments').type), 'list<item: string>')
        self.assertEqual(str(record.SCHEMA.field('address_missing').type), 'bool')
        self.assertEqual(FEATURE_VERSION, 'feat_v2_0')

    def test_build_row_length_and_types_match_the_schema(self):
        row = record.build_row('S2-77', 'ACME LLC', '5 Main Rd, Bangor, ME', 'US', comparison_key('ACME LLC'), comparison_key('5 Main Rd, Bangor, ME'),
                               'train', 2, FEATURE_VERSION, HYGIENE_VERSION)
        self.assertEqual(len(row), len(record.COLUMNS))
        pa.Table.from_arrays([pa.array([v], type=f.type) for v, f in zip(row, record.SCHEMA)], schema=record.SCHEMA)   # raises if any type is off


if __name__ == '__main__':
    unittest.main()
