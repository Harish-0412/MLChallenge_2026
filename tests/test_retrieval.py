"""Retrieval engine tests: every channel kind is checked against an independent pure-Python brute force on a synthetic corpus written as
Parquet (so corpus loading and query sampling are exercised too), plus leakage, determinism and evaluator checks."""
import hashlib
import math
import random
import re
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import MAX_K, engine, evaluate  # noqa: E402
from validation import scorer  # noqa: E402

WORDS = [f'w{i}' for i in range(40)] + ['acme', 'global', 'trading', 'stores', 'kumar', 'sharma', 'llc', 'ltd']
COUNTRY = 'India'


def make_corpus(tmp: Path, n_queries=400, n_targets=1500, seed=11):
    rng = random.Random(seed)
    weights = [1.0 / (i + 1) for i in range(len(WORDS))]

    def name():
        return ' '.join(rng.choices(WORDS, weights, k=rng.randint(1, 4)))

    def address():
        toks = [str(rng.randint(1, 60)), rng.choice(['road', 'street', 'lane']), rng.choice(WORDS), rng.choice(['pune', 'delhi', 'mumbai'])]
        return ' '.join(toks)

    def record(eid):
        nm, ad = name(), (address() if rng.random() > 0.1 else '')
        toks = ad.split() if ad else []
        return {'entity_id': eid, 'country': COUNTRY, 'name_key': nm, 'address_key': ad, 'name_core': nm, 'name_core_compact': nm.replace(' ', ''),
                'name_skeleton': re.sub('[aeiou ]', '', nm), 'name_translit': nm, 'address_canon': ad, 'address_tokset': ' '.join(sorted(set(toks))),
                'address_postal_candidates': [t for t in toks if t.isdigit() and len(t) >= 2][:2], 'address_numbers_canon': [t for t in toks if t.isdigit()][:2],
                'address_missing': ad == ''}
    queries = [record(f'S1-{i}') for i in range(n_queries)]
    targets = [record(f'S{2 + i % 2}-{i}') for i in range(n_targets)]
    # make some targets exact copies of queries so equality channels have real hits
    for i in range(0, n_queries, 3):
        copy = dict(queries[i])
        copy['entity_id'] = f'S2-{n_targets + i}'
        targets.append(copy)
    feat = tmp / 'feat' / 'split=train' / 'source=1' / f'country={COUNTRY}'
    feat.mkdir(parents=True)
    tfeat = tmp / 'feat' / 'split=train' / 'source=2' / f'country={COUNTRY}'
    tfeat.mkdir(parents=True)
    columns = engine.FEATURE_COLUMNS
    schema_types = {'address_postal_candidates': pa.list_(pa.string()), 'address_numbers_canon': pa.list_(pa.string()), 'address_missing': pa.bool_()}

    def write(rows, path):
        arrays = {c: pa.array([r[c] for r in rows], type=schema_types.get(c, pa.string())) for c in columns}
        pq.write_table(pa.table(arrays), path)
    write(queries, feat / 'p.parquet')
    write(targets, tfeat / 'p.parquet')
    man_rows = []
    for i, q in enumerate(queries):
        man_rows.append({'entity_id': q['entity_id'], 'role': 'query', 'country': COUNTRY, 'fold': 'dev' if i % 5 else 'val', 'stratum': f'{COUNTRY}|{i % 3}',
                         'match_count': i % 3})
    for i, t in enumerate(targets):
        man_rows.append({'entity_id': t['entity_id'], 'role': 'target', 'country': COUNTRY, 'fold': 'dev' if i % 6 else 'val', 'stratum': 'x', 'match_count': None})
    pq.write_table(pa.table({k: [r[k] for r in man_rows] for k in man_rows[0]}), tmp / 'manifest.parquet')
    return queries, targets, man_rows


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='retr_'))
        cls.queries, cls.targets, cls.man = make_corpus(cls.tmp)
        cls.manifest = (cls.tmp / 'manifest.parquet').as_posix()
        cls.glob = (cls.tmp / 'feat' / 'split=train' / 'source=*' / f'country={COUNTRY}' / '*.parquet').as_posix()
        cls.con = duckdb.connect()
        cls.digest = engine.sample_queries(cls.con, cls.manifest, n=120)
        cls.sizes = engine.load_corpus(cls.con, cls.glob, cls.manifest, COUNTRY)
        cls.dev_targets = sorted(r['entity_id'] for r in cls.man if r['role'] == 'target' and r['fold'] == 'dev')
        cls.tid = {e: i + 1 for i, e in enumerate(cls.dev_targets)}                    # tid = rank of entity_id (binary order)
        cls.bench_ids = sorted(r[0] for r in cls.con.execute('SELECT id FROM bench_q').fetchall())
        cls.qid = {e: i + 1 for i, e in enumerate(cls.bench_ids)}
        cls.trec = {t['entity_id']: t for t in cls.targets}
        cls.qrec = {q['entity_id']: q for q in cls.queries}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def channel_rows(self, name):
        return self.con.execute('SELECT qid, tid, rnk, score FROM cand WHERE channel = ? ORDER BY qid, rnk', [name]).fetchall()

    # ------------------------------------------------------------------ sampling
    def test_query_sample_matches_an_independent_python_implementation(self):
        n = 120
        dev = [r for r in self.man if r['role'] == 'query' and r['fold'] == 'dev']
        sizes = Counter(r['stratum'] for r in dev)
        total = sum(sizes.values())
        quota = {s: math.floor(n * c / total) for s, c in sizes.items()}
        leftover = n - sum(quota.values())
        fracs = sorted(sizes, key=lambda s: (-(n * sizes[s] / total - quota[s]), s))
        for s in fracs[:leftover]:
            quota[s] += 1
        expected = set()
        for s in sizes:
            members = sorted((hashlib.sha256(f'{engine.SEED}|bench|{r["entity_id"]}'.encode()).hexdigest(), r['entity_id']) for r in dev if r['stratum'] == s)
            expected |= {e for _h, e in members[:quota[s]]}
        self.assertEqual(set(self.bench_ids), expected)
        self.assertEqual(len(self.bench_ids), n)
        self.assertTrue(all(self.qrec[q] for q in self.bench_ids))
        self.assertEqual(self.sizes['queries'], n)

    def test_corpus_is_the_dev_targets_only(self):
        self.assertEqual(self.sizes['targets'], len(self.dev_targets))
        ids = {r[0] for r in self.con.execute('SELECT entity_id FROM tt').fetchall()}
        self.assertEqual(ids, set(self.dev_targets))
        self.assertTrue(all(i.startswith(('S2-', 'S3-')) for i in ids))

    # ------------------------------------------------------------------ equality channels
    def brute_equality(self, key_of, secondary, cap):
        expected = {}
        by_key = {}
        for tid_, eid in ((self.tid[e], e) for e in self.dev_targets):
            k = key_of(self.trec[eid])
            if k:
                by_key.setdefault(k, []).append(tid_)
        for q in self.bench_ids:
            k = key_of(self.qrec[q])
            block = by_key.get(k, []) if k else []
            if len(block) > cap:
                scored = sorted(((-secondary(self.qrec[q], self.trec[self.dev_targets[t - 1]]), t) for t in block))
                ranked = [(t, -s) for s, t in scored]
            else:
                ranked = [(t, 1.0) for t in sorted(block)]
            expected[self.qid[q]] = ranked[:MAX_K]
        return expected

    def test_equality_channels_equal_a_brute_force(self):
        def jaccard(a, b):
            x, y = set(a['address_tokset'].split()), set(b['address_tokset'].split())
            return 0.0 if not x or not y else len(x & y) / len(x | y)
        con = self.con
        con.execute("DELETE FROM cand")
        con.execute("DELETE FROM chan_stats")
        engine.equality_channel(con, 'eq_name_key', 'name_key', engine.ADDR_JACCARD, cap=5)
        engine.equality_channel(con, 'eq_address_key', 'address_key', None, cap=5)
        engine.equality_channel(con, 'eq_core_number', "CASE WHEN num1 IS NULL THEN NULL ELSE name_core_compact || '|' || num1 END", None, cap=5)
        for name, key_of, sec in (('eq_name_key', lambda r: r['name_key'], jaccard), ('eq_address_key', lambda r: r['address_key'], lambda a, b: 1.0),
                                  ('eq_core_number', lambda r: (r['name_core_compact'] + '|' + r['address_numbers_canon'][0]) if r['address_numbers_canon'] else None, lambda a, b: 1.0)):
            want = self.brute_equality(key_of, sec, 5)
            got = {}
            for qid, tid, rnk, score in self.channel_rows(name):
                got.setdefault(qid, []).append((tid, score))
            for qid in want:
                self.assertEqual([t for t, _s in got.get(qid, [])], [t for t, _s in want[qid]], (name, qid))
                for (_t, gs), (_t2, ws) in zip(got.get(qid, []), want[qid]):
                    self.assertAlmostEqual(gs, ws, places=9)
        self.assertGreater(con.execute("SELECT count(*) FROM cand WHERE channel = 'eq_name_key'").fetchone()[0], 0)
        self.assertGreater(con.execute("SELECT oversize_blocks FROM chan_stats WHERE channel = 'eq_name_key'").fetchone()[0], 0, 'the test must exercise oversize blocks')

    # ------------------------------------------------------------------ postings channels
    def th(self, tok):
        return self.con.execute('SELECT hash(?)', [tok]).fetchone()[0]

    def brute_postings(self, tok_of, df_cap, rarest):
        docs = {self.tid[e]: {t for t in tok_of(self.trec[e]) if t} for e in self.dev_targets}
        df = Counter(t for toks in docs.values() for t in toks)
        n = len(docs)
        idf = {t: math.floor(math.log((n + 1.0) / (c + 0.5)) * 1e6 + 0.5) for t, c in df.items() if c <= df_cap}
        postings = {}
        for tid_, toks in docs.items():
            for t in toks:
                if t in idf:
                    postings.setdefault(t, []).append(tid_)
        expected = {}
        for q in self.bench_ids:
            qt = sorted(((-idf[t], self.th(t), t) for t in {t for t in tok_of(self.qrec[q]) if t} if t in idf))[:rarest]
            scores = {}
            for neg, _h, t in qt:
                for tid_ in postings.get(t, []):
                    scores[tid_] = scores.get(tid_, 0) - neg
            expected[self.qid[q]] = [(t, -neg / 1e6) for neg, t in sorted(((-s, t) for t, s in scores.items()))][:MAX_K]
        return expected

    def test_postings_channels_equal_a_brute_force(self):
        con = self.con
        con.execute("DELETE FROM cand")
        engine.postings_channel(con, 'tok_name', 'n_toks', df_cap=200, rarest=3)
        engine.postings_channel(con, 'tok_address', 'a_toks', df_cap=150, rarest=4)
        cases = (('tok_name', lambda r: r['name_translit'].split(' '), 200, 3), ('tok_address', lambda r: r['address_tokset'].split(' '), 150, 4))
        for name, tok_of, cap, rarest in cases:
            want = self.brute_postings(tok_of, cap, rarest)
            got = {}
            for qid, tid, rnk, score in self.channel_rows(name):
                got.setdefault(qid, []).append((tid, score, rnk))
            self.assertGreater(len(got), 10)
            for qid, expected in want.items():
                self.assertEqual([t for t, _s, _r in got.get(qid, [])], [t for t, _s in expected], (name, qid))
                for (_t, gs, gr), (_t2, ws), i in zip(got.get(qid, []), expected, range(1, MAX_K + 1)):
                    self.assertAlmostEqual(gs, ws, places=9)
                    self.assertEqual(gr, i)

    def test_rarest_tokens_bound_the_work_and_stop_tokens_are_ignored(self):
        con = self.con
        con.execute("DELETE FROM cand")
        engine.postings_channel(con, 'tok_name', 'n_toks', df_cap=2, rarest=5)          # only tokens found in <= 2 targets survive
        n = con.execute("SELECT count(*) FROM cand").fetchone()[0]
        con.execute("DELETE FROM cand")
        engine.postings_channel(con, 'tok_name', 'n_toks', df_cap=100000, rarest=5)
        self.assertGreater(con.execute("SELECT count(*) FROM cand").fetchone()[0], n)

    # ------------------------------------------------------------------ evaluator
    def test_evaluator_matches_python_metrics(self):
        con = self.con
        con.execute("DELETE FROM cand")
        engine.equality_channel(con, 'eq_name_key', 'name_key', engine.ADDR_JACCARD)
        engine.postings_channel(con, 'tok_address', 'a_toks', df_cap=150, rarest=4)
        rng = random.Random(5)
        truth = {}
        for q in self.bench_ids:
            truth[q] = set(rng.sample(self.dev_targets, rng.choice([0, 0, 1, 2, 4])))
        # give the truth some overlap with the candidates so recall is non-trivial
        for q in self.bench_ids[::2]:
            rows = con.execute('SELECT tid FROM cand WHERE qid = ? AND channel = ? LIMIT 2', [self.qid[q], 'eq_name_key']).fetchall()
            truth[q] |= {self.dev_targets[r[0] - 1] for r in rows}
        con.execute('CREATE OR REPLACE TABLE bench_q2 AS SELECT * FROM bench_q')
        cand = con.execute("SELECT c.channel, q.entity_id AS q, t.entity_id AS t, c.rnk, c.score FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid)").fetchall()
        ev = duckdb.connect()
        ev.execute('CREATE TABLE cand (channel VARCHAR, q VARCHAR, t VARCHAR, rnk INT, score DOUBLE)')
        ev.executemany('INSERT INTO cand VALUES (?, ?, ?, ?, ?)', cand)
        ev.execute('CREATE TABLE bench_q AS SELECT * FROM (VALUES ' + ', '.join(f"('{q}', '{COUNTRY}')" for q in self.bench_ids) + ') t(id, country)')
        ev.execute('CREATE TABLE truth (q VARCHAR, t VARCHAR)')
        ev.executemany('INSERT INTO truth VALUES (?, ?)', [(q, t) for q, ts in truth.items() for t in ts])
        spec = {'eq_name_key': 100, 'tok_address': 10}
        got = evaluate.evaluate(ev, spec)
        sel = {q: set() for q in self.bench_ids}
        for ch, q, t, rnk, _s in cand:
            if rnk <= spec[ch]:
                sel[q].add(t)
        links = sum(len(v) for v in truth.values())
        hits = sum(len(truth[q] & sel[q]) for q in truth)
        self.assertEqual((got['links'], got['hits'], got['pairs']), (links, hits, sum(len(v) for v in sel.values())))
        non = [q for q in truth if truth[q]]
        self.assertAlmostEqual(got['macro_recall_nonsingleton'], sum(len(truth[q] & sel[q]) / len(truth[q]) for q in non) / len(non), places=12)
        self.assertAlmostEqual(got['all_links_coverage'], sum(truth[q] <= sel[q] for q in non) / len(non), places=12)
        self.assertAlmostEqual(got['zero_candidate_rate'], sum(not sel[q] for q in truth) / len(truth), places=12)
        oracle = scorer.macro_f05_sets({q: sorted(v) for q, v in truth.items()}, {q: sorted(truth[q] & sel[q]) for q in truth})['macro_f05']
        self.assertAlmostEqual(got['oracle_macro_f05'], oracle, places=12)
        by_slice = evaluate.missed_by_slice.__doc__
        self.assertIn('Missed', by_slice)

    # ------------------------------------------------------------------ hygiene
    def test_engine_never_touches_a_label(self):
        source = (ROOT / 'src' / 'retrieval' / 'engine.py').read_text(encoding='utf-8').lower()
        for forbidden in ('truth', 'ground_truth', 'label', 'matched_entity'):
            self.assertNotIn(forbidden, source, forbidden)

    def test_channels_are_deterministic(self):
        con = self.con
        results = []
        for _ in range(2):
            con.execute("DELETE FROM cand")
            engine.equality_channel(con, 'eq_name_key', 'name_key', engine.ADDR_JACCARD)
            engine.postings_channel(con, 'tri_name', 'n_tri', df_cap=300, rarest=6)
            results.append(con.execute('SELECT * FROM cand ORDER BY channel, qid, rnk, tid').fetchall())
        self.assertEqual(results[0], results[1])
        self.assertGreater(len(results[0]), 100)


if __name__ == '__main__':
    unittest.main()
