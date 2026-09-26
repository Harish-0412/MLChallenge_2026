"""Scorer and fold-manifest tests (protocol val_v1) on a synthetic universe, including sabotage tests for every leakage check."""
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from modeling.metrics import f05_for_sets  # noqa: E402  (the other, independently written scorer)
from validation import leakage, scorer, splits  # noqa: E402


class ScorerTests(unittest.TestCase):
    """The six documented cases, on both implementations."""
    CASES = [(set(), set(), 1.0), (set(), {'S2-1'}, 0.0), ({'S2-1'}, set(), 0.0), ({'S2-1', 'S2-2'}, {'S2-1', 'S2-2'}, 1.0),
             ({'S2-1', 'S2-2'}, {'S2-1', 'S2-2', 'S3-3'}, 5 / 7), ({'S2-1', 'S2-2'}, {'S2-1'}, 5 / 6)]

    def test_documented_cases_sets(self):
        for truth, pred, expected in self.CASES:
            self.assertAlmostEqual(scorer.entity_f05(truth, pred), expected, places=12)
            self.assertAlmostEqual(scorer.macro_f05_sets({'S1-1': truth}, {'S1-1': pred})['macro_f05'], expected, places=12)

    def test_documented_cases_duckdb(self):
        con = duckdb.connect()
        for truth, pred, expected in self.CASES:
            con.execute("CREATE OR REPLACE TEMP TABLE qs AS SELECT 'S1-1' AS id")
            con.execute('CREATE OR REPLACE TEMP TABLE tr (q VARCHAR, t VARCHAR)')
            con.execute('CREATE OR REPLACE TEMP TABLE pr (q VARCHAR, t VARCHAR)')
            for t in truth:
                con.execute("INSERT INTO tr VALUES ('S1-1', ?)", [t])
            for t in pred:
                con.execute("INSERT INTO pr VALUES ('S1-1', ?)", [t])
            self.assertAlmostEqual(scorer.macro_f05_tables(con, 'qs', 'tr', 'pr')['macro_f05'], expected, places=12)

    def test_macro_average_counts_every_query_including_empty_predictions(self):
        truth = {'S1-1': ['S2-1'], 'S1-2': [], 'S1-3': ['S2-2', 'S3-2']}
        pred = {'S1-1': ['S2-1'], 'S1-2': [], 'S1-3': []}
        result = scorer.macro_f05_sets(truth, pred)
        self.assertAlmostEqual(result['macro_f05'], (1 + 1 + 0) / 3)
        self.assertEqual((result['queries'], result['singletons'], result['perfect_queries']), (3, 1, 2))

    def test_invalid_inputs_are_rejected(self):
        truth = {'S1-1': ['S2-1'], 'S1-2': []}
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_sets(truth, {'S1-1': ['S2-1', 'S2-1'], 'S1-2': []})            # duplicate ids
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_sets(truth, {'S1-1': ['S2-1']})                                # missing query
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_sets(truth, {'S1-1': [], 'S1-2': [], 'S1-9': []})              # extra query
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_sets(truth, {'S1-1': ['S1-7'], 'S1-2': []})                    # a target must be S2/S3
        con = duckdb.connect()
        con.execute("CREATE TABLE qs AS SELECT * FROM (VALUES ('S1-1'), ('S1-2')) t(id)")
        con.execute("CREATE TABLE tr AS SELECT * FROM (VALUES ('S1-1', 'S2-1')) t(q, t)")
        con.execute("CREATE TABLE dup AS SELECT * FROM (VALUES ('S1-1', 'S2-1'), ('S1-1', 'S2-1')) t(q, t)")
        con.execute("CREATE TABLE unk AS SELECT * FROM (VALUES ('S1-9', 'S2-1')) t(q, t)")
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_tables(con, 'qs', 'tr', 'dup')
        with self.assertRaises(scorer.ScorerInputError):
            scorer.macro_f05_tables(con, 'qs', 'tr', 'unk')

    def test_three_implementations_agree_on_random_data(self):
        rng = random.Random(7)
        targets = [f'S{2 + i % 2}-{i}' for i in range(40)]
        truth, pred = {}, {}
        for i in range(300):
            q = f'S1-{i}'
            truth[q] = set(rng.sample(targets, rng.choice([0, 0, 1, 2, 3, 5])))
            pred[q] = set(rng.sample(sorted(truth[q]), rng.randint(0, len(truth[q])))) | set(rng.sample(targets, rng.choice([0, 0, 1, 2])))
            self.assertAlmostEqual(scorer.entity_f05(truth[q], pred[q]), f05_for_sets(truth[q], pred[q]), places=12)
        by_sets = scorer.macro_f05_sets(truth, {q: sorted(v) for q, v in pred.items()})['macro_f05']
        con = duckdb.connect()
        con.execute('CREATE TABLE qs (id VARCHAR)')
        con.execute('CREATE TABLE tr (q VARCHAR, t VARCHAR)')
        con.execute('CREATE TABLE pr (q VARCHAR, t VARCHAR)')
        con.executemany('INSERT INTO qs VALUES (?)', [(q,) for q in truth])
        con.executemany('INSERT INTO tr VALUES (?, ?)', [(q, t) for q, ts in truth.items() for t in ts])
        con.executemany('INSERT INTO pr VALUES (?, ?)', [(q, t) for q, ts in pred.items() for t in ts])
        self.assertAlmostEqual(scorer.macro_f05_tables(con, 'qs', 'tr', 'pr')['macro_f05'], by_sets, places=12)

    def test_all_empty_baseline_is_the_singleton_fraction(self):
        truth = {f'S1-{i}': (['S2-1'] if i % 4 else []) for i in range(100)}
        result = scorer.macro_f05_sets(truth, {q: [] for q in truth})
        self.assertAlmostEqual(result['macro_f05'], 25 / 100)


def build_universe(con, n_s1=2400, seed=3):
    rng = random.Random(seed)
    s1, targets, pairs, next_t = [], [], [], 1
    for i in range(n_s1):
        country = 'India' if i % 3 else 'US'
        eid = f'S1-{i}'
        s1.append((eid, country, f'name{i % 400}'))
        for _ in range(rng.choice([0, 0, 1, 1, 1, 2, 2, 3, 4, 5, 7])):
            source = rng.choice([2, 3])
            tid = f'S{source}-{next_t}'
            next_t += 1
            targets.append((tid, source, country))
            pairs.append((eid, tid))
    for _ in range(1500):                                                                    # unmatched distractors
        source = rng.choice([2, 3])
        targets.append((f'S{source}-{next_t}', source, rng.choice(['India', 'US'])))
        next_t += 1
    con.register('s1_df', pa.table({'entity_id': [r[0] for r in s1], 'country': [r[1] for r in s1], 'name_key': [r[2] for r in s1]}))
    con.register('t_df', pa.table({'entity_id': [r[0] for r in targets], 'source': [r[1] for r in targets], 'country': [r[2] for r in targets]}))
    con.register('p_df', pa.table({'source1_entity_id': [p[0] for p in pairs], 'target_id': [p[1] for p in pairs]}))
    con.execute('CREATE VIEW s1 AS SELECT entity_id, country FROM s1_df')
    con.execute('CREATE VIEW s1_keys AS SELECT * FROM s1_df')
    con.execute('CREATE VIEW targets AS SELECT * FROM t_df')
    con.execute('CREATE VIEW truth_pairs AS SELECT * FROM p_df')


class FoldManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='folds_'))
        cls.con = duckdb.connect()
        build_universe(cls.con)
        cls.main = (cls.tmp / 'main.parquet').as_posix()
        cls.stress = (cls.tmp / 'stress.parquet').as_posix()
        splits.build_manifest(cls.con, cls.main, fullcorpus_sample=100)
        splits.build_stress_manifest(cls.con, cls.stress)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_checks(self, main=None, **kw):
        return leakage.run_checks(self.con, main or self.main, stress_manifest=self.stress, documented_singleton_fraction=None, **kw)

    def failed(self, checks):
        return [n.split()[0] for n, ok, _d in checks if not ok]

    def test_clean_manifest_passes_every_check(self):
        checks = self.run_checks()
        self.assertEqual(self.failed(checks), [], checks)
        self.assertGreaterEqual(len(checks), 15)

    def test_build_is_deterministic(self):
        again = (self.tmp / 'again.parquet').as_posix()
        splits.build_manifest(self.con, again, fullcorpus_sample=100)
        query = "SELECT sha256(string_agg(role || entity_id || fold, ',' ORDER BY role, entity_id)) FROM read_parquet('{}')"
        self.assertEqual(self.con.execute(query.format(again)).fetchone(), self.con.execute(query.format(self.main)).fetchone())

    def test_proportions_are_80_10_10_per_stratum(self):
        rows = self.con.execute(f"SELECT stratum, fold, count(*) FROM read_parquet('{self.main}') WHERE role = 'query' GROUP BY 1, 2").fetchall()
        sizes = {}
        for stratum, fold, n in rows:
            sizes.setdefault(stratum, {})[fold] = n
        for stratum, by_fold in sizes.items():
            total = sum(by_fold.values())
            self.assertEqual(by_fold.get('dev', 0), total * 8 // 10, stratum)
            self.assertEqual(by_fold.get('dev', 0) + by_fold.get('val', 0), total * 9 // 10, stratum)
        self.assertEqual({s.split('|')[1] for s in sizes}, set(splits.BUCKETS))

    def test_python_rule_reproduces_the_sql_rule(self):
        rows = self.con.execute(f"SELECT entity_id, stratum, fold FROM read_parquet('{self.main}') WHERE role = 'query'").fetchall()
        want = splits.assign_folds_python([(e, s) for e, s, _f in rows], 'query')
        self.assertTrue(all(want[e] == f for e, _s, f in rows))

    def test_seed_changes_the_assignment(self):
        rows = self.con.execute(f"SELECT entity_id, stratum, fold FROM read_parquet('{self.main}') WHERE role = 'query'").fetchall()
        other = splits.assign_folds_python([(e, s) for e, s, _f in rows], 'query', seed='another-seed')
        self.assertGreater(sum(other[e] != f for e, _s, f in rows), len(rows) * 0.2)

    def test_stress_groups_keep_same_names_together(self):
        n = self.con.execute(f"""SELECT count(*) FROM (SELECT k.name_key FROM read_parquet('{self.stress}') s JOIN s1_keys k USING (entity_id)
                                 WHERE s.role = 'query' GROUP BY k.country, k.name_key HAVING count(DISTINCT s.fold) > 1)""").fetchone()[0]
        self.assertEqual(n, 0)

    # ------------------------------------------------------------------------------------------ sabotage
    def sabotage(self, mutate_sql):
        table = self.con.execute(f"SELECT * FROM read_parquet('{self.main}')").fetch_arrow_table()
        path = (self.tmp / 'sabotaged.parquet').as_posix()
        self.con.register('m_tmp', table)
        self.con.execute(f"COPY ({mutate_sql}) TO '{path}' (FORMAT PARQUET)")
        self.con.unregister('m_tmp')
        return path

    def test_a_target_moved_to_another_fold_is_a_leak(self):
        path = self.sabotage("""SELECT * REPLACE (CASE WHEN entity_id = (SELECT min(entity_id) FROM m_tmp WHERE role = 'target' AND assignment = 'owner'
                                 AND fold = 'dev') AND role = 'target' THEN 'holdout' ELSE fold END AS fold) FROM m_tmp""")
        failed = self.failed(self.run_checks(path))
        self.assertIn('L5', failed)

    def test_a_wrong_owner_is_caught(self):
        path = self.sabotage("""SELECT * REPLACE (CASE WHEN entity_id = (SELECT min(entity_id) FROM m_tmp WHERE assignment = 'owner')
                                 THEN 'S1-WRONG' ELSE owner_id END AS owner_id) FROM m_tmp""")
        self.assertIn('L6', self.failed(self.run_checks(path)))

    def test_a_missing_entity_is_caught(self):
        path = self.sabotage("SELECT * FROM m_tmp WHERE entity_id <> (SELECT min(entity_id) FROM m_tmp WHERE role = 'query')")
        self.assertIn('L2', self.failed(self.run_checks(path)))

    def test_a_query_moved_within_its_fold_structure_breaks_proportions_and_the_recompute(self):
        path = self.sabotage("""SELECT * REPLACE (CASE WHEN role = 'query' AND fold = 'dev' AND entity_id = (SELECT min(entity_id) FROM m_tmp WHERE role = 'query' AND fold = 'dev')
                                 THEN 'val' ELSE fold END AS fold) FROM m_tmp""")
        failed = self.failed(self.run_checks(path))
        self.assertTrue({'L8', 'L10'} <= set(failed), failed)

    def test_an_invalid_fold_value_is_caught(self):
        path = self.sabotage("SELECT * REPLACE ('train' AS fold) FROM m_tmp")
        self.assertIn('L4', self.failed(self.run_checks(path)))


if __name__ == '__main__':
    unittest.main()
