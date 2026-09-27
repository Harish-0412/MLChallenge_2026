"""Decision policies, evaluator and feature guard of src/ranking, checked against independent brute-force implementations."""
import itertools
import random
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ranking import model as rm  # noqa: E402
from ranking import pairs as rp  # noqa: E402
from validation import scorer  # noqa: E402


def random_problem(seed=3, n_queries=300):
    rng = random.Random(seed)
    qcodes, probs, labels = [], [], []
    n_true = np.zeros(n_queries)
    for q in range(n_queries):
        n_true[q] = rng.choice([0, 0, 1, 2, 3, 5])
        n_c = rng.randint(0, 9)
        n_pos = min(int(n_true[q]), n_c, rng.randint(0, 5))
        lab = [1] * n_pos + [0] * (n_c - n_pos)
        rng.shuffle(lab)
        for l in lab:
            qcodes.append(q)
            probs.append(min(0.999, max(0.001, (0.7 if l else 0.25) + rng.uniform(-0.25, 0.25))))
            labels.append(l)
    perm = list(range(len(qcodes)))
    rng.shuffle(perm)                                             # rows are NOT sorted by query
    return (np.array([qcodes[i] for i in perm]), np.array([probs[i] for i in perm]), np.array([labels[i] for i in perm], dtype=np.int8), n_true)


class DecisionTests(unittest.TestCase):
    def test_threshold_selection_equals_brute_force(self):
        q, p, y, n = random_problem()
        for tau, k, margin in itertools.product((0.2, 0.5, 0.8), (1, 3, 12), (0.0, 0.15)):
            got = rm.select_threshold(q, p, tau, k, margin)
            want = np.zeros(len(p), bool)
            for code in np.unique(q):
                rows = np.flatnonzero(q == code)
                order = sorted(rows, key=lambda r: (-p[r], r))
                second = p[order[1]] if len(order) > 1 else 0.0
                if p[order[0]] - second >= margin:
                    chosen = [r for r in order if p[r] >= tau][:k]
                    want[chosen] = True
            self.assertTrue((got == want).all(), (tau, k, margin))

    def test_expected_f_selection_equals_brute_force(self):
        q, p, y, n = random_problem(seed=9)
        got = rm.select_expected_f(q, p, recall_est=0.95, top_k=6, empty_bias=0.02)
        want = np.zeros(len(p), bool)
        for code in np.unique(q):
            rows = sorted(np.flatnonzero(q == code), key=lambda r: (-p[r], r))
            pi = np.array([p[r] for r in rows])
            p_empty, total = float(np.prod(1 - pi)), pi.sum() / 0.95
            best_v, best_m = -1, 0
            for m in range(1, min(6, len(pi)) + 1):
                s = pi[:m].sum()
                v = (1 - p_empty) * 1.25 * s / (1.25 * s + (m - s) + 0.25 * max(total - s, 0))
                if v > best_v:
                    best_v, best_m = v, m
            if best_v > p_empty + 0.02:
                want[rows[:best_m]] = True
        self.assertTrue((got == want).all())

    def test_macro_f05_matches_the_set_based_scorer_including_empty_queries(self):
        q, p, y, n = random_problem(seed=5)
        sel = rm.select_threshold(q, p, 0.5, 4)
        # build truth so that its size equals n_true: the labelled candidates are true links, the rest are links the retrieval missed
        truth, pred = {}, {}
        for code in range(len(n)):
            rows = np.flatnonzero(q == code)
            true_ids = [f'S2-{code * 100000 + int(r)}' for r in rows if y[r] == 1]
            missed = int(n[code]) - len(true_ids)
            if missed < 0:                                       # labels exceed n_true in the generator: raise n_true
                n[code] = len(true_ids)
                missed = 0
            truth[f'S1-{code}'] = true_ids + [f'S3-{code * 100000 + 90000 + i}' for i in range(missed)]
            pred[f'S1-{code}'] = [f'S2-{code * 100000 + int(r)}' for r in rows if sel[r]]
        got = rm.macro_f05_from_selection(q, y, sel, n)
        ref = scorer.macro_f05_sets(truth, pred)['macro_f05']
        self.assertAlmostEqual(got, ref, places=12)

    def test_all_empty_selection_scores_the_singleton_fraction(self):
        q, p, y, n = random_problem(seed=4)
        self.assertAlmostEqual(rm.macro_f05_from_selection(q, y, np.zeros(len(q), bool), n), float((n == 0).mean()))

    def test_oracle_selection_is_perfect_when_nothing_is_missed(self):
        q = np.array([0, 0, 1, 2, 2])
        y = np.array([1, 0, 1, 0, 0], dtype=np.int8)
        n = np.array([1, 1, 0])
        self.assertAlmostEqual(rm.macro_f05_from_selection(q, y, y == 1, n), (1 + 1 + 1) / 3)


class GuardTests(unittest.TestCase):
    def test_model_features_exclude_ids_labels_and_query_level_facts(self):
        self.assertEqual(rp.assert_model_features(rp.MODEL_FEATURES), rp.MODEL_FEATURES)
        for bad in ('entity_id', 'is_positive', 'match_count', 'true_match_count', 'fold', 'evidence_slice', 's1_entity_id', 'sample_weight', 'country'):
            with self.assertRaises(ValueError):
                rp.assert_model_features(['name_hyg_ratio', bad])
        with self.assertRaises(ValueError):
            rp.assert_model_features(['name_hyg_ratio', 'name_hyg_ratio'])
        self.assertFalse(set(rp.MODEL_FEATURES) & rp.FORBIDDEN)
        self.assertEqual(len(rp.MODEL_FEATURES), len(set(rp.MODEL_FEATURES)))

    def test_stable_bucket_is_deterministic_and_roughly_uniform(self):
        ids = [f'S1-{i}' for i in range(5000)]
        a = [rm.stable_bucket(i, 's') for i in ids]
        self.assertEqual(a, [rm.stable_bucket(i, 's') for i in ids])
        self.assertNotEqual(a, [rm.stable_bucket(i, 't') for i in ids])
        self.assertAlmostEqual(np.mean(np.array(a) < 80), 0.8, delta=0.03)


class OneOwnerTests(unittest.TestCase):
    def test_competitor_max_equals_brute_force(self):
        from ranking import owner
        rng = random.Random(2)
        n = 400
        pairs = rng.sample([(a, b) for a in range(60) for b in range(80)], n)          # a (query, target) pair occurs once, as in real candidate sets
        q = np.array([a for a, _b in pairs])
        t = np.array([b for _a, b in pairs])
        p = np.array([rng.random() for _ in range(n)])
        got = owner.competitor_max(t, q, p)
        for i in range(n):
            others = [p[j] for j in range(n) if t[j] == t[i] and q[j] != q[i]]
            self.assertAlmostEqual(got[i], max(others, default=0.0), places=12)

    def test_rule_keeps_the_most_probable_owner_only(self):
        from ranking import owner
        q = np.array([0, 1, 2, 0])
        t = np.array([7, 7, 8, 9])
        p = np.array([0.6, 0.9, 0.8, 0.7])
        sel = np.ones(4, bool)
        self.assertEqual(owner.apply_one_owner(sel, t, q, p).tolist(), [False, True, True, True])
        self.assertEqual(owner.apply_one_owner(sel, t, q, p, margin=0.5).tolist(), [True, True, True, True])         # margin 0.5 tolerates the 0.3 gap
        unsel = np.array([True, False, True, True])
        self.assertEqual(owner.apply_one_owner(unsel, t, q, p, among='selected').tolist(), [True, False, True, True])   # the competitor was not selected
        self.assertEqual(owner.apply_one_owner(unsel, t, q, p, among='all').tolist(), [False, False, True, True])


if __name__ == '__main__':
    unittest.main()
