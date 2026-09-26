import json
import random
import re
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import addresses as A  # noqa: E402
from cleaning import lexicons as L  # noqa: E402
from cleaning import text_hygiene as h  # noqa: E402
from cleaning import translit as T  # noqa: E402
from normalization import comparison_key as v1  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'address_fixtures_v2.jsonl'
INTERIM = ROOT / 'data' / 'interim'


def feats(raw, country, **kw):
    return A.build_address_features(raw, country, **kw)


class FixtureTests(unittest.TestCase):
    """Verbatim data addresses and synthetic edge cases with hand-derived expectations (address_fixtures_v2.jsonl)."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = [json.loads(l) for l in FIXTURES.read_text(encoding='utf-8').splitlines() if l.strip()]

    def test_shape(self):
        self.assertGreaterEqual(len(self.fixtures), 60)
        self.assertEqual({f['kind'] for f in self.fixtures}, {'pair', 'one'})
        self.assertEqual(len({f['case'] for f in self.fixtures}), len(self.fixtures), 'case names must be unique')
        self.assertGreaterEqual(sum(f['kind'] == 'pair' for f in self.fixtures), 10)

    def test_real_true_pairs(self):
        for f in (x for x in self.fixtures if x['kind'] == 'pair'):
            a, b = feats(f['a'], f['country']), feats(f['b'], f['country'])
            for check in f['checks']:
                if check['field'] == 'address_key_v1':
                    left, right = v1(f['a']), v1(f['b'])
                else:
                    left, right = a[check['field']], b[check['field']]
                self.assertEqual(left == right, check['equal'], f"{f['case']} {f['ids']} {check['field']}: {left!r} vs {right!r}")
                if check['equal']:
                    self.assertNotEqual(left, '', f['case'])

    def test_single_addresses_and_synthetic_cases(self):
        for f in (x for x in self.fixtures if x['kind'] == 'one'):
            record = feats(f['raw'], f['country'])
            for key, expected in f['expect'].items():
                self.assertEqual(record[key], expected, f"{f['case']} [{f['id']}] {key} for {f['raw']!r}")


class LexiconTests(unittest.TestCase):
    def tearDown(self):
        for fn in (L.state_forms, L.state_canonicals, L.address_abbrev, L.address_placeholder_segments, L.address_noise_tokens, L.address_noise_patterns,
                   L.address_noise_number_tokens, L.address_noise_segment_words):
            fn.cache_clear()

    def patch_states(self, rows):
        data = [{'country': c, 'form': f, 'canonical': k, 'kind': kind, 'observed_s1': '0', 'observed_s2': '0', 'observed_s3': '0', 'evidence': ''} for c, f, k, kind in rows]
        L.state_forms.cache_clear()
        return mock.patch.object(L, 'read_lexicon', lambda name: data if name == 'states.tsv' else [])

    def test_shipped_lexicons_load_and_scope(self):
        self.assertEqual(len(L.state_canonicals('India')), 16)
        self.assertEqual(len(L.state_canonicals('France')), 3)
        self.assertGreaterEqual(len(L.state_canonicals('US')), 45)
        self.assertEqual(L.state_forms('Atlantis'), {})
        self.assertEqual(L.address_abbrev('India'), {})            # no abbreviation family has evidence in India
        self.assertEqual(L.address_abbrev('Atlantis'), {})
        self.assertEqual(L.address_abbrev('US')['st'], ('street', 'suffix'))
        self.assertEqual(L.address_abbrev('France')['st'], ('saint', 'any'))
        self.assertEqual(L.address_placeholder_segments(), frozenset({'null', 'n a'}))
        self.assertEqual(L.address_placeholder_segments('India'), frozenset({'null', 'n a', 'divreportingcircle'}))
        self.assertEqual(L.address_placeholder_segments('France'), frozenset({'null', 'n a'}))
        self.assertEqual(L.address_abbrev('US')['ct'], ('court', 'suffix_multi'))
        self.assertNotIn('sq', L.address_abbrev('US'), 'sq failed the evidence threshold (2,793 < 3,000 multi-token segments)')
        self.assertEqual(L.address_noise_tokens('US'), frozenset({'cdp', 'pmb'}))
        self.assertEqual(L.address_noise_tokens('India'), frozenset({'b3'}))
        self.assertEqual(L.address_noise_number_tokens('India'), frozenset({'hn'}))
        self.assertEqual(L.address_noise_number_tokens('US'), frozenset())
        self.assertEqual(L.address_noise_segment_words('India'), frozenset({'region'}))
        self.assertEqual(L.address_noise_segment_words('US'), frozenset())

    def test_every_india_state_has_a_name_a_code_and_a_native_form(self):
        by_canon = {}
        for form, (canon, kind) in L.state_forms('India').items():
            by_canon.setdefault(canon, set()).add(kind)
        self.assertEqual(len(by_canon), 16)
        for canon, kinds in by_canon.items():
            self.assertTrue({'name', 'code', 'native'} <= kinds, (canon, kinds))
        native = [f for f, (_c, k) in L.state_forms('India').items() if k == 'native']
        self.assertEqual(len(native), 16)
        for form in native:
            self.assertTrue(T.has_indic(T.script_mask(form)), form)

    def test_bad_state_lexicons_are_rejected(self):
        with self.patch_states([('US', 'ny', 'new york', 'code')]):
            with self.assertRaisesRegex(L.LexiconError, "no 'name' row"):
                L.state_forms('US')
        with self.patch_states([('US', 'ny', 'new york', 'code'), ('US', 'ny', 'new york', 'code'), ('US', 'new york', 'new york', 'name')]):
            with self.assertRaisesRegex(L.LexiconError, 'duplicate'):
                L.state_forms('US')
        with self.patch_states([('US', 'NY', 'new york', 'code'), ('US', 'new york', 'new york', 'name')]):
            with self.assertRaisesRegex(L.LexiconError, 'lower-case'):
                L.state_forms('US')
        with self.patch_states([('US', 'ny', 'new york', 'bogus'), ('US', 'new york', 'new york', 'name')]):
            with self.assertRaisesRegex(L.LexiconError, 'unknown kind'):
                L.state_forms('US')


class BehaviourTests(unittest.TestCase):
    def test_zero_stripping_helpers(self):
        for raw, expected in [('00936', '936'), ('g02', 'g2'), ('0', '0'), ('00', '0'), ('10', '10'), ('abc', 'abc'), ('5-0105', '5-105'), ('0012a', '12a')]:
            self.assertEqual(A._strip_zeros(raw), expected, raw)
        self.assertEqual(A.canon_number('C-251'), 'c251')
        self.assertEqual(A.canon_number('J 105'), 'j105')
        self.assertEqual(A.canon_number('5 bis'), '5bis')
        self.assertEqual(A.canon_number('0012'), '12')
        self.assertNotEqual(A.canon_number('5-105'), A.canon_number('5105'))

    def test_label_dropping_can_be_switched_off_and_keeps_the_context(self):
        on, off = feats('Door No 377, Mumbai, MH', 'India'), feats('Door No 377, Mumbai, MH', 'India', drop_labels=False)
        self.assertEqual(on['address_canon'], 'door 377 mumbai maharashtra')
        self.assertEqual(off['address_canon'], 'door no 377 mumbai maharashtra')
        self.assertEqual(on['address_number_ctx'], off['address_number_ctx'])

    def test_a_label_separated_from_its_number_by_a_comma_gives_the_same_view_as_the_inline_form(self):
        comma, inline = feats('Plot No, 93, Sector 5, Pune, Maharashtra', 'India'), feats('Plot No 93, Sector 5, Pune, Maharashtra', 'India')
        for key in ('address_canon', 'address_tokset'):
            self.assertEqual(comma[key], inline[key])
        self.assertNotEqual(comma['address_segset'], inline['address_segset'], 'the segment structure itself is kept')
        self.assertIn('no', feats('Plot No, 93, Pune', 'India', drop_labels=False)['address_canon'].split())

    def test_the_letter_n_is_not_a_label(self):
        """A unit letter must survive: ``Apartment N, 6724 Derby Dr`` keeps ``n`` (tried as a label: no gain on true pairs, real harm here)."""
        self.assertEqual(feats('Apartment N, 6724 Derby Dr, Gurnee, IL', 'US')['address_canon'], 'apartment n 6724 derby drive gurnee illinois')
        self.assertEqual(feats('Block N 5, Pune', 'India')['address_canon'], 'block n 5 pune')

    def test_canon_of_canon_is_a_fixed_point_for_label_edge_cases(self):
        for raw in ('No, No, 4, Pune', 'Hissa No., 12, Dharwad', 'Plot No, 93', 'No, No, No', 'Gate N, 5 Main Road', 'H. No., 830, Sector-15, Faridabad, Haryana'):
            once = feats(raw, 'India')['address_canon']
            self.assertEqual(feats(once, 'India')['address_canon'], once, raw)

    def test_injected_components_can_be_kept_for_ablation(self):
        kept = feats('140 Main Ave, PO BOX 2989, Appleton, WI', 'US', remove_extras=False)
        self.assertIn('box', kept['address_canon'].split())
        self.assertEqual(kept['address_extras'], '')
        self.assertNotIn('box', feats('140 Main Ave, PO BOX 2989, Appleton, WI', 'US')['address_canon'].split())

    def test_p_o_box_with_dots_is_also_removed_in_the_us_only(self):
        self.assertEqual(feats('1 A St, P.O. Box 12, Austin, TX', 'US')['address_extras'], 'p o box 12')
        self.assertIn('box', feats('1 A St, P.O. Box 12, Austin, TX', 'India')['address_canon'].split())

    def test_state_lookup_is_whole_segment_only(self):
        self.assertEqual(feats('Stay in Hotel, Austin', 'US')['address_state_canon'], '')     # the word "in" is not Indiana
        self.assertEqual(feats('IN', 'US')['address_state_canon'], 'indiana')

    def test_the_known_telangana_andhra_pradesh_pair_is_two_distinct_states(self):
        self.assertNotEqual(feats('Nizamabad, Telangana', 'India')['address_state_canon'], feats('Nizamabad, Andhra Pradesh', 'India')['address_state_canon'])

    def test_columns_types_and_no_none(self):
        record = feats('5 Main St, Austin, TX', 'US')
        self.assertEqual(tuple(record), A.ADDRESS_COLUMNS)
        for key, value in record.items():
            self.assertIsNotNone(value, key)
            self.assertIsInstance(value, (str, int, bool, list), key)
        self.assertEqual(tuple(feats('', 'US')), A.ADDRESS_COLUMNS)

    def test_missing_address_has_every_view_empty(self):
        for raw in ['', '   ', '\t']:
            record = feats(raw, 'US')
            self.assertEqual(record['address_parse_conf'], 'missing')
            for key, value in record.items():
                if key not in ('address_parse_conf', 'address_state_conf'):
                    self.assertIn(value, ('', [], 0, False), (key, value))

    def test_canonical_segments_are_idempotent(self):
        for raw, country in [('22 Champlain Ave, Lewiston, ME', 'US'), ('FLAT NO: G02, తెలంగాణ, HYDERABAD, DOOR NO:3-6-611/2', 'India'),
                             ('27 ALL DES CHÈVREFEUILLES, ST-NAZAIRE, Loire-Atlantique', 'France'), ('140 TELULAH AVENUE, PO BOX 2989, CITY OF APPLETON, WI', 'US')]:
            once = feats(raw, country)
            again = feats(', '.join(once['address_segments']), country)
            self.assertEqual(again['address_segments'], once['address_segments'], raw)

    def test_set_views_are_order_insensitive(self):
        a = feats('1009 Mt Vernon Avenue, Charlotte, NC', 'US')
        b = feats('Charlotte, 1009 Mt Vernon Avenue, NC', 'US')
        self.assertEqual(a['address_tokset'], b['address_tokset'])
        self.assertEqual(a['address_segset'], b['address_segset'])
        self.assertNotEqual(a['address_canon'], b['address_canon'])

    def test_native_script_state_is_the_only_non_latin_content_after_canonicalisation(self):
        record = feats('OM SADNIKA 1ST FLOORPLOT NO 265/1 PANVEL-URAN ROAD PANVEL, RAIGAD, महाराष्ट्र', 'India')
        self.assertTrue(record['address_canon'].isascii())
        self.assertEqual(record['address_state_canon'], 'maharashtra')

    def test_scripts_mask_matches_the_raw_text(self):
        for raw in ['Pune, महाराष्ट्र', '5 Main St', '']:
            self.assertEqual(feats(raw, 'India')['address_scripts'], T.script_mask(raw) if raw.strip() else 0)


class ScopingMutationTests(unittest.TestCase):
    def test_without_suffix_multi_a_whole_segment_ct_would_stop_being_connecticut(self):
        """Mutation: the plain ``suffix`` rule expands the state code CT to Court; suffix_multi is what keeps the state."""
        with mock.patch.object(A, 'address_abbrev', lambda country: {'ct': ('court', 'suffix')}):
            broken = feats('104 Fairview Dr, Wethersfield, CT', 'US')
        self.assertEqual((broken['address_state_canon'], broken['address_segments'][-1]), ('', 'court'))
        good = feats('104 Fairview Dr, Wethersfield, CT', 'US')
        self.assertEqual((good['address_state_canon'], good['address_segments'][-1]), ('connecticut', 'connecticut'))

    def test_removing_the_india_noise_rules_changes_the_fixtures_views(self):
        raw = 'HN 711 Ground Floor, B3/12, Pune Region, Divreportingcircle, Pune, Maharashtra'
        good = feats(raw, 'India')
        self.assertEqual(good['address_canon'], 'ground floor 12 pune maharashtra')
        self.assertEqual((good['address_extras'], good['address_null_tokens']), ('hn 711 | b3 | pune region', 1))
        with mock.patch.object(A, 'address_noise_number_tokens', lambda country: frozenset()):
            self.assertIn('hn 711', feats(raw, 'India')['address_canon'])
        with mock.patch.object(A, 'address_noise_segment_words', lambda country: frozenset()):
            self.assertIn('pune region', feats(raw, 'India')['address_segments'])
        with mock.patch.object(A, 'address_noise_tokens', lambda country: frozenset()):
            self.assertIn('b3', feats(raw, 'India')['address_canon'].split())
        with mock.patch.object(A, 'address_placeholder_segments', lambda country='': frozenset({'null', 'n a'})):
            self.assertIn('divreportingcircle', feats(raw, 'India')['address_canon'])

    def test_india_noise_rules_do_not_touch_other_countries(self):
        raw = 'HN 711 Ground Floor, B3/12, Pune Region, Divreportingcircle, Pune, Maharashtra'
        for country in ('US', 'France', 'Elbonia'):
            canon = feats(raw, country)['address_canon']
            for token in ('hn', 'b3', 'region', 'divreportingcircle'):
                self.assertIn(token, canon.split(), (country, token))

    def test_zeros_are_stripped_before_the_noise_rules(self):
        """``B03`` is ``b3`` for the noise rule; otherwise the canon of the canon would drop it a second time."""
        once = feats('Suite B03, H-15 Sector-63, Noida, UP', 'India')['address_canon']
        self.assertEqual(once, 'suite h 15 sector 63 noida uttar pradesh')
        self.assertEqual(feats(once, 'India')['address_canon'], once)

    def test_removing_the_cross_segment_rule_breaks_the_fixtures(self):
        """Mutation: without the cross-segment pass 'Plot No, 93' keeps its 'no' and the canon of the canon changes again."""
        with mock.patch.object(A, '_drop_labels_across_segments', lambda token_lists: [t for t in token_lists if t]):
            self.assertEqual(feats('Plot No, 93, Sector 5, Pune, Maharashtra', 'India')['address_canon'], 'plot no 93 sector 5 pune maharashtra')
            once = feats('Plot No, 93, Pune', 'India')['address_canon']
            self.assertNotEqual(feats(once, 'India')['address_canon'], once)

    def test_a_lexicon_without_scoping_would_break_the_fixtures(self):
        """If US abbreviations leaked into India, 5 Main Rd would change: guards the country tiers."""
        with mock.patch.object(A, 'address_abbrev', lambda country: L.address_abbrev('US')):
            self.assertEqual(feats('5 Main Rd, Bangor, ME', 'India')['address_canon'], '5 main road bangor me')


@unittest.skipUnless((INTERIM / 'test_source1.parquet').exists(), 'data/interim not available')
class RealDataSampleTests(unittest.TestCase):
    """~100k deterministic rows over all files: structural invariants of the address features."""

    @classmethod
    def setUpClass(cls):
        import duckdb
        con = duckdb.connect()
        con.execute("SET memory_limit='2GB'")
        con.execute('SET threads=2')
        cls.rows = []
        for table in ['train_source1', 'train_source2', 'train_source3', 'test_source1', 'test_source2', 'test_source3']:
            cls.rows += con.execute(f"""SELECT business_address, country, address_key FROM read_parquet('{(INTERIM / (table + '.parquet')).as_posix()}')
                WHERE hash(entity_id) % 240 = 0""").fetchall()
        con.close()

    def test_invariants(self):
        for raw, country, address_key in self.rows:
            cleaned, _ = h.clean_text(raw)
            r = feats(raw, country, cleaned=cleaned)
            if raw.strip() == '':
                self.assertEqual(r['address_parse_conf'], 'missing')
                self.assertEqual(r['address_canon'], '')
                continue
            # digits are never lost or invented: cleaned digit runs == canonical runs + digit runs of the removed injected components
            cleaned_runs = Counter(A._ZERO_RUN.sub('', x) for x in re.findall(r'\d+', cleaned))
            canon_runs = Counter(re.findall(r'\d+', r['address_canon']))
            extra_runs = Counter(A._ZERO_RUN.sub('', x) for x in re.findall(r'\d+', r['address_extras']))
            self.assertEqual(cleaned_runs, canon_runs + extra_runs, raw)
            # spans
            raws, canons, ctxs = r['address_numbers_raw'], r['address_numbers_canon'], r['address_number_ctx']
            self.assertEqual(len(raws), len(canons))
            self.assertEqual(len(raws), len(ctxs))
            for span, canon in zip(raws, canons):
                self.assertIn(span, cleaned, raw)
                self.assertEqual(canon, A.canon_number(span))
            # states
            if r['address_state_canon']:
                self.assertIn(r['address_state_canon'], L.state_canonicals(country))
                self.assertIn(r['address_state_conf'], ('exact', 'alias', 'mapped_native', 'mapped_department'))
            else:
                self.assertIn(r['address_state_conf'], ('none', 'conflict'))
            # confidence rules
            found = bool(r['address_state_canon'])
            expected = 'high' if found and raws else 'medium' if found or raws else 'low'
            self.assertEqual(r['address_parse_conf'], expected, raw)
            self.assertEqual(r['address_had_leading_zero'], re.search(r'(?<!\d)0\d+', cleaned) is not None)
            self.assertEqual(r['address_scripts'], T.script_mask(raw))
            self.assertEqual(r['address_tokset'], ' '.join(sorted(set(r['address_canon'].split()))))
            self.assertEqual(r['address_nsegments'], len(r['address_segments']))
            self.assertLessEqual(len(r['address_city_candidates']), 3)
            self.assertEqual(r['address_postal_candidates'], sorted(set(r['address_postal_candidates'])))
            # nothing valid becomes empty unless it consisted only of injected components
            if address_key and not r['address_canon']:
                self.assertTrue(r['address_null_tokens'] or r['address_extras'], raw)

    def test_canon_text_is_a_fixed_point_on_real_rows(self):
        """The stricter form: the space-joined canon (segment boundaries gone) must canonicalise to itself."""
        checked = 0
        for raw, country, _k in self.rows[::3]:
            if not raw.strip():
                continue
            once = feats(raw, country)['address_canon']
            self.assertEqual(feats(once, country)['address_canon'], once, raw)
            checked += 1
        self.assertGreater(checked, 20_000)

    def test_canonical_segments_idempotent_on_real_rows(self):
        for raw, country, _k in self.rows[::7]:
            if not raw.strip():
                continue
            once = feats(raw, country)
            self.assertEqual(feats(', '.join(once['address_segments']), country)['address_segments'], once['address_segments'], raw)


if __name__ == '__main__':
    unittest.main()
