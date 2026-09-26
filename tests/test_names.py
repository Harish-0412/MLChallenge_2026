import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import lexicons as L  # noqa: E402
from cleaning import names as N  # noqa: E402
from cleaning import text_hygiene as h  # noqa: E402
from normalization import comparison_key as v1  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'name_fixtures_v2.jsonl'
INTERIM = ROOT / 'data' / 'interim'


def feats(raw, country):
    return N.build_name_features(raw, country)


class FixtureTests(unittest.TestCase):
    """Verbatim data strings and synthetic edge cases with hand-written expectations (name_fixtures_v2.jsonl)."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = [json.loads(l) for l in FIXTURES.read_text(encoding='utf-8').splitlines() if l.strip()]

    def test_fixture_file_shape(self):
        self.assertGreaterEqual(len(self.fixtures), 60)
        self.assertEqual({f['kind'] for f in self.fixtures}, {'pair', 'one'})
        self.assertEqual(len({f['case'] for f in self.fixtures}), len(self.fixtures), 'case names must be unique')

    def test_real_pairs(self):
        pairs = [f for f in self.fixtures if f['kind'] == 'pair']
        self.assertGreaterEqual(len(pairs), 12)
        for f in pairs:
            a = feats(f['a'], f['country'])[f['a_field']]
            b = feats(f['b'], f['country'])[f['b_field']]
            self.assertEqual(a == b, f['expect_equal'], f"{f['case']} {f['ids']}: {a!r} vs {b!r}")
            self.assertEqual(v1(f['a']) == v1(f['b']), f['v1_equal'], f"{f['case']}: the v1 key must not already agree")
            if f['expect_equal']:
                self.assertNotEqual(a, '', f['case'])

    def test_single_names_and_synthetic_cases(self):
        for f in (x for x in self.fixtures if x['kind'] == 'one'):
            record = feats(f['raw'], f['country'])
            for key, expected in f['expect'].items():
                self.assertEqual(record[key], expected, f"{f['case']} [{f['id']}] {key} for {f['raw']!r}")


class LexiconValidationTests(unittest.TestCase):
    def tearDown(self):
        for fn in (L._legal_rows, L.legal_index_for_tier, L.noise_tokens, L._country_tiers):
            fn.cache_clear()

    def with_legal_rows(self, rows):
        header = [{'tier': t, 'token': k, 'code': c, 'rank': str(r), 'observed_count': '0', 'evidence': ''} for t, k, c, r in rows]
        L._legal_rows.cache_clear()
        return mock.patch.object(L, 'read_lexicon', lambda name: header if name == 'legal_forms.tsv' else [])

    def test_shipped_lexicons_load_and_are_consistent(self):
        rows = L._legal_rows()
        self.assertGreater(len(rows), 20)
        by_tier = Counter(t for t, *_ in rows)
        self.assertTrue({'generic', 'US', 'IN', 'FR'} <= set(by_tier))
        self.assertEqual(L.country_tier('India'), 'IN')
        self.assertIsNone(L.country_tier('Atlantis'))

    def test_duplicate_token_in_tier_is_rejected(self):
        with self.with_legal_rows([('generic', 'ltd', 'LTD', 20), ('generic', 'ltd', 'LTD', 20)]):
            with self.assertRaisesRegex(L.LexiconError, 'duplicate'):
                L._legal_rows()

    def test_token_with_two_codes_is_rejected(self):
        with self.with_legal_rows([('generic', 'co', 'CO', 50), ('US', 'co', 'COMPANY', 50)]):
            with self.assertRaisesRegex(L.LexiconError, 'two codes'):
                L._legal_rows()

    def test_code_with_two_ranks_is_rejected(self):
        with self.with_legal_rows([('generic', 'ltd', 'LTD', 20), ('generic', 'limited', 'LTD', 21)]):
            with self.assertRaisesRegex(L.LexiconError, 'two ranks'):
                L._legal_rows()

    def test_unknown_tier_and_bad_tokens_are_rejected(self):
        for bad in [('XX', 'ltd', 'LTD', 20), ('generic', 'Ltd', 'LTD', 20), ('generic', 'two words', 'LTD', 20)]:
            with self.with_legal_rows([bad]):
                with self.assertRaises(L.LexiconError):
                    L._legal_rows()

    def test_country_scoping_of_the_shipped_lexicon(self):
        self.assertIn('private', L.legal_index('India'))
        self.assertNotIn('private', L.legal_index('US'))
        self.assertNotIn('private', L.legal_index('Atlantis'))
        self.assertIn('sci', L.legal_index('France'))
        self.assertNotIn('sci', L.legal_index('US'))
        self.assertNotIn('sci', L.legal_index('India'))
        self.assertIn('llc', L.legal_index('Atlantis'))            # generic tier applies everywhere
        self.assertIn('pllc', L.legal_index('US'))
        self.assertNotIn('pllc', L.legal_index('France'))

    def test_noise_and_placeholder_lexicons(self):
        self.assertEqual(L.noise_tokens('leading'), frozenset({'the', 'dr', 'mr', 'sri', 'shri', 'smt'}))
        self.assertEqual(L.noise_tokens('connector'), frozenset({'and'}))
        self.assertEqual(L.noise_tokens('leading_pattern'), frozenset({'m/s'}))
        self.assertEqual(L.placeholder_names(), frozenset({'na', 'n/a', 'null', 'none', 'nan', 'unknown', '-'}))

    def test_generic_tokens_are_per_country_and_exclude_legal_words(self):
        for country in ['US', 'India', 'France']:
            generic = L.generic_tokens(country)
            self.assertGreater(len(generic), 50, country)
            self.assertFalse(generic & set(L.legal_index(country)), country)
            self.assertFalse(generic & L.noise_tokens('leading'), country)
        self.assertEqual(L.generic_tokens('Atlantis'), frozenset())


class BehaviourTests(unittest.TestCase):
    def test_ninformative_counts_core_tokens_outside_the_generic_list(self):
        for raw, country in [('Pediatric Associates Zyxwv LLC', 'US'), ('Green Global Marketing Pvt Ltd', 'India'), ('Maison Xyzzy SARL', 'France')]:
            record = feats(raw, country)
            generic = L.generic_tokens(country)
            self.assertEqual(record['name_ninformative'], sum(1 for t in record['name_core'].split() if t not in generic), raw)
            self.assertLessEqual(record['name_ninformative'], record['name_ncore'])
        self.assertEqual(feats('Zyxwv Qwerty', 'Atlantis')['name_ninformative'], 2)   # no list for an unknown country

    def test_core_is_a_subsequence_of_the_hygiene_tokens(self):
        for raw, country in [('The Foo and Bar Private Limited', 'India'), ('Dr Modern Enterprises LLP', 'India'), ('LLC TBN Innovative Fund', 'US'),
                             ('Mcube (India) Apparels Private', 'India'), ('globalclassicsouthwest.com', 'US')]:
            record = feats(raw, country)
            hyg = h.hygiene_record(raw, '')['name_hyg'].split()
            it = iter(hyg)
            self.assertTrue(all(tok in it for tok in record['name_core'].split()), (raw, hyg, record['name_core']))
            self.assertEqual(record['name_ntokens'], len(hyg))

    def test_core_is_idempotent(self):
        for raw, country in [('Dr M/s The Foo & Bar Pvt. Ltd.', 'India'), ('LLC', 'US'), ('SCI Les Pins', 'France'), ('www.foo.com', 'US'),
                             ('Whatley LLC Services', 'US'), ('Foo límited', 'India'), ('The The Foo', 'US'), ('and and', 'US')]:
            once = feats(raw, country)
            again = feats(once['name_core'], country)
            self.assertEqual(again['name_core'], once['name_core'], raw)

    def test_columns_are_stable_and_never_none(self):
        record = feats('Acme Ltd', 'India')
        self.assertEqual(tuple(record), N.NAME_COLUMNS)
        for key, value in record.items():
            self.assertIsInstance(value, (str, int, bool), key)
        self.assertEqual(json.loads(record['name_token_counts']), {})

    def test_no_new_v1_split_of_legal_form_tokens(self):
        # v1 turns L.L.C. into three tokens; the production tokens keep it whole, so a legal form is recognised
        self.assertEqual(v1('Bison L.L.C.'), 'bison l l c')
        self.assertEqual(feats('Bison L.L.C.', 'US')['legal_form'], 'LLC')

    def test_name_core_fold_only_folds_latin_and_ligatures(self):
        self.assertEqual(feats('Café Cœur Ltd', 'US')['name_core_fold'], 'cafe coeur')
        self.assertEqual(feats('Café Cœur Ltd', 'US')['name_core'], 'café cœur')
        self.assertEqual(feats('आदित्य ट्रेडिंग', 'India')['name_core_fold'], 'आदित्य ट्रेडिंग')

    def test_appended_noise_trim_is_country_scoped_experimental_and_never_empties(self):
        for country in ('US', 'India', 'France'):
            noise = sorted(L.appended_noise(country))
            self.assertGreater(len(noise), 3, country)
            self.assertFalse(set(noise) & set(L.legal_index(country)), country)
            word = noise[0]
            record = feats(f'Zorblax {word}', country)
            self.assertEqual(record['name_core'], f'zorblax {word}')            # the core keeps it
            self.assertEqual(record['name_core_trim'], 'zorblax', country)       # the experimental view drops it
            self.assertEqual(feats(word, country)['name_core_trim'], word)      # never remove the only token
            self.assertEqual(feats(f'Zorblax {word} {word}', country)['name_core_trim'], 'zorblax')
        self.assertEqual(feats('Zorblax Services', 'Atlantis')['name_core_trim'], 'zorblax services')   # no list for unknown countries
        us_only = sorted(L.appended_noise('US') - L.appended_noise('India'))[0]
        self.assertEqual(feats(f'Zorblax {us_only}', 'India')['name_core_trim'], f'zorblax {us_only}')

    def test_domain_only_for_com(self):
        for raw in ['sujata.com', 'SUJATA.COM', 'a-b.c-d.com']:
            self.assertTrue(feats(raw, 'India')['name_is_domain_like'], raw)
        for raw in ['sujata.org', 'Sujata .com', 'sujata.commerce', 'St.Mary.church']:
            self.assertFalse(feats(raw, 'India')['name_is_domain_like'], raw)


@unittest.skipUnless((INTERIM / 'test_source1.parquet').exists(), 'data/interim not available')
class RealDataSampleTests(unittest.TestCase):
    """A deterministic sample (~100k rows over all files): structural invariants of the name features."""

    @classmethod
    def setUpClass(cls):
        import duckdb
        con = duckdb.connect()
        con.execute("SET memory_limit='2GB'")
        con.execute('SET threads=2')
        cls.rows = []
        for table in ['train_source1', 'train_source2', 'train_source3', 'test_source1', 'test_source2', 'test_source3']:
            cls.rows += con.execute(f"""SELECT business_name, country FROM read_parquet('{(INTERIM / (table + '.parquet')).as_posix()}')
                WHERE hash(entity_id) % 240 = 0""").fetchall()
        con.close()

    def test_invariants(self):
        codes = {code for _t, _tok, code, _r in L._legal_rows()}
        for raw, country in self.rows:
            r = feats(raw, country)
            hyg = h.hygiene_record(raw, '')['name_hyg'].split()
            self.assertEqual(r['name_ntokens'], len(hyg), raw)
            self.assertNotEqual(r['name_core'], '', raw)                       # never an empty core for a real name
            it = iter(hyg)
            self.assertTrue(all(tok in it for tok in r['name_core'].split()), raw)
            if r['name_core_fallback']:
                self.assertEqual(r['name_core'].split(), hyg, raw)
                self.assertNotEqual(r['legal_form'], '', raw)
            self.assertTrue(set(filter(None, r['legal_form'].split('+'))) <= codes, raw)
            self.assertEqual(r['legal_form'] == '', r['legal_form_pos'] == 'none', raw)
            self.assertEqual(r['name_ncore'], len(r['name_core'].split()), raw)
            self.assertLessEqual(r['name_ninformative'], r['name_ncore'], raw)
            self.assertEqual(sorted(set(r['name_core'].split())), r['name_core_set'].split(), raw)
            self.assertEqual(r['name_core'].replace(' ', ''), r['name_core_compact'], raw)
            if r['name_is_domain_like']:
                self.assertTrue(raw.strip().lower().endswith('.com'), raw)

    def test_core_idempotent_on_real_rows(self):
        for raw, country in self.rows[::5]:
            once = feats(raw, country)
            self.assertEqual(feats(once['name_core'], country)['name_core'], once['name_core'], raw)


if __name__ == '__main__':
    unittest.main()
