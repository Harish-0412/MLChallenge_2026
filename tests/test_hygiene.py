import json
import random
import sys
import unicodedata
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import text_hygiene as h  # noqa: E402
from cleaning.lexicons import legal_dotted, lexicon_sha256, read_lexicon  # noqa: E402
from normalization import comparison_key  # noqa: E402  (frozen v1 rule)

FIXTURES = ROOT / 'tests' / 'fixtures' / 'hygiene_fixtures_v2.jsonl'
INTERIM = ROOT / 'data' / 'interim'


def load_fixtures():
    return [json.loads(line) for line in FIXTURES.read_text(encoding='utf-8').splitlines() if line.strip()]


class V1ParityTests(unittest.TestCase):
    """lmn_key is the frozen v1 rule; it may be faster but must never differ."""

    CASES = ['École', 'École', 'आदित्य ट्रेडिंग प्रा. लि.', 'महाराष्ट्र', 'A & B Ltd.', '', '  No.5-105\t', 'a_b', 'İstanbul',
             'ΑΣ Σίγμα', '5 bis', 'ಕನ್‌ಸ್ಟ್ರಕ್ಷನ್', 'straße', 'ǅ', 'x y', 'Nº 5', '½ litre', '\x1a', 'Â\x80\x93', 'ＡＢＣ']

    def test_lmn_key_equals_v1_comparison_key(self):
        for text in self.CASES:
            self.assertEqual(h.lmn_key(text), comparison_key(text), repr(text))

    def test_lmn_key_ascii_fast_path_matches_v1_on_random_ascii(self):
        rng = random.Random(1)
        alphabet = [chr(c) for c in range(32, 127)] + ['\t']
        for _ in range(3000):
            text = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            self.assertEqual(h.lmn_key(text), comparison_key(text), repr(text))

    def test_lmn_key_matches_v1_on_random_unicode(self):
        rng = random.Random(2)
        pools = [range(0x20, 0x250), range(0x900, 0x980), range(0xC80, 0xCFF), range(0x2000, 0x2070), range(0x3000, 0x3040)]
        for _ in range(3000):
            pool = rng.choice(pools)
            text = ''.join(chr(rng.choice(pool)) for _ in range(rng.randint(0, 25)))
            self.assertEqual(h.lmn_key(text), comparison_key(text), repr(text))


class PrimitiveTests(unittest.TestCase):
    def test_fold_latin_removes_latin_accents_and_ligatures_only(self):
        self.assertEqual(h.fold_latin('École'), 'Ecole')
        self.assertEqual(h.fold_latin('Cœur'), 'Coeur')
        self.assertEqual(h.fold_latin('Straße'), 'Strasse')
        self.assertEqual(h.fold_latin('Łódź'), 'Lodz')
        self.assertEqual(h.fold_latin('आदित्य ट्रेडिंग'), 'आदित्य ट्रेडिंग')
        self.assertEqual(h.fold_latin('École आदित्य'), 'Ecole आदित्य')
        self.assertEqual(h.fold_latin('École'), 'Ecole')           # decomposed input
        self.assertEqual(h.fold_latin('ಕನ್ಸ್ಟ್ರಕ್ಷನ್'), 'ಕನ್ಸ್ಟ್ರಕ್ಷನ್')

    def test_remove_joiners_deletes_without_space(self):
        self.assertEqual(h.remove_joiners('ಕನ್‌ಸ್'), 'ಕನ್ಸ್')
        self.assertEqual(h.remove_joiners('a‍b'), 'ab')
        self.assertEqual(len(h.lmn_key(h.remove_joiners('ಕನ್‌ಸ್ಟ್ರ')).split()), 1)
        self.assertEqual(len(h.lmn_key('ಕನ್‌ಸ್ಟ್ರ').split()), 2)     # the v1 defect this fixes

    def test_repair_controls(self):
        self.assertEqual(h.collapse_ws(h.repair_controls('Plot Â\x80\x93 148')), 'Plot 148')
        self.assertEqual(h.collapse_ws(h.repair_controls('Blockâ\x80\x93A')), 'Block A')
        self.assertEqual(h.collapse_ws(h.repair_controls('Sector \x1a 54')), 'Sector 54')
        self.assertEqual(h.repair_controls('Chennai\x1aBangalore'), 'Chennai Bangalore')

    def test_lead_character_is_only_removed_before_a_c1_control(self):
        self.assertEqual(h.repair_controls('château\x1a2'), 'château 2')          # legitimate â kept
        self.assertEqual(h.repair_controls('Âne'), 'Âne')
        self.assertEqual(h.repair_controls('École'), 'École')

    def test_french_accents_and_indic_text_are_never_treated_as_mojibake(self):
        for text in ['Fédération du Sud-Ouest', 'Mérignac', 'Église Saint-Étienne', 'महाराष्ट्र', 'Ñandú', 'Ça va']:
            self.assertEqual(h.repair_controls(text), text)
            self.assertFalse(h.has_mojibake(text))
            self.assertFalse(h.has_control(text))

    def test_normalize_punctuation(self):
        self.assertEqual(h.normalize_punctuation('l’Eglise'), "l'Eglise")
        self.assertEqual(h.normalize_punctuation('a–b—c−d'), 'a-b-c-d')
        self.assertEqual(h.normalize_punctuation('N°5'), 'No 5')
        self.assertEqual(h.normalize_punctuation('N° 5'), 'No 5')
        self.assertEqual(h.normalize_punctuation('nº12'), 'no 12')
        self.assertEqual(h.normalize_punctuation('Nº 5 rue'), 'No 5 rue')
        self.assertEqual(h.normalize_punctuation('1º étage'), '1° étage')
        self.assertEqual(h.normalize_punctuation('45° nord'), '45° nord')              # degree sign left alone
        self.assertEqual(h.normalize_punctuation('MONO°5'), 'MONO°5')                  # N is inside a word
        self.assertEqual(h.normalize_punctuation('N°A'), 'N°A')                        # not followed by a digit

    def test_join_dotted_legal_only_for_lexicon_forms(self):
        self.assertEqual(h.join_dotted_legal('Bison  L.L.C.'), 'Bison  LLC')
        self.assertEqual(h.join_dotted_legal('Sun Industries L.L.P.'), 'Sun Industries LLP')
        self.assertEqual(h.join_dotted_legal('Fractales S.A.S'), 'Fractales SAS')
        self.assertEqual(h.join_dotted_legal('Fils S.A.R.L.'), 'Fils SARL')
        self.assertEqual(h.join_dotted_legal('Smith, M.D.'), 'Smith, MD')
        self.assertEqual(h.join_dotted_legal('J. R. Smith'), 'J. R. Smith')            # spaced initials
        self.assertEqual(h.join_dotted_legal('J.R. Smith'), 'J.R. Smith')              # jr is not in the lexicon
        self.assertEqual(h.join_dotted_legal('K.G.N. Plaza'), 'K.G.N. Plaza')
        self.assertEqual(h.join_dotted_legal('l.l.c.'), 'llc')
        self.assertEqual(h.join_dotted_legal('AL.L.C'), 'AL.L.C')                      # starts inside a word

    def test_join_apostrophes(self):
        self.assertEqual(h.join_apostrophes("l'Eglise l’ocean Women's"), 'lEglise locean Womens')

    def test_collapse_ws_handles_unicode_spaces(self):
        self.assertEqual(h.collapse_ws(' a   b\t\tc '), 'a b c')

    def test_flags(self):
        self.assertTrue(h.has_control('a\x1ab'))
        self.assertFalse(h.has_control('plain text é'))
        self.assertTrue(h.has_format('ಕನ್‌ಸ್'))
        self.assertFalse(h.has_format('plain'))
        self.assertTrue(h.has_mojibake('x\x80y'))
        self.assertTrue(h.has_mojibake('x\x1ay'))
        self.assertFalse(h.has_mojibake('x\x01y'))          # other controls are has_control but not the dash-corruption pattern
        self.assertTrue(h.has_control('x\x01y'))
        self.assertTrue(h.has_multispace('a  b'))
        self.assertFalse(h.has_multispace('a b'))
        self.assertFalse(h.has_multispace(' a b '))

    def test_unicode_compat_view_differs_from_nfc_only_for_compat_characters(self):
        rec = h.hygiene_record('ＡＢＣ Ltd', '')
        self.assertEqual(rec['name_compat_key'], 'abc ltd')
        self.assertEqual(rec['name_hyg'], 'ａｂｃ ltd')
        plain = h.hygiene_record('Abc Ltd', '')
        self.assertEqual(plain['name_compat_key'], plain['name_hyg'])


class LexiconTests(unittest.TestCase):
    def test_dotted_lexicon_is_lowercase_unique_and_hashed(self):
        rows = read_lexicon('legal_dotted.tsv')
        forms = [r['collapsed'] for r in rows]
        self.assertEqual(len(forms), len(set(forms)))
        self.assertTrue(all(f == f.lower() and f.isalpha() for f in forms))
        self.assertEqual({r['category'] for r in rows}, {'legal', 'credential', 'dba'})
        self.assertEqual(legal_dotted(), frozenset(forms))
        self.assertEqual(len(lexicon_sha256('legal_dotted.tsv')), 64)

    def test_lexicon_covers_the_forms_named_in_the_evidence(self):
        for form in ['llc', 'pc', 'llp', 'pllc', 'sas', 'sarl', 'eurl', 'sasu', 'sci', 'snc', 'pa']:
            self.assertIn(form, legal_dotted())


class FixtureTests(unittest.TestCase):
    """Verbatim data strings with hand-written expectations (tests/fixtures/hygiene_fixtures_v2.jsonl)."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_fixtures()

    def test_fixture_file_is_not_empty_and_kinds_are_known(self):
        self.assertGreaterEqual(len(self.fixtures), 30)
        self.assertEqual({f['kind'] for f in self.fixtures}, {'pair_equal', 'expect', 'tokens'})

    def test_pairs_become_equal_where_v1_key_was_not(self):
        pairs = [f for f in self.fixtures if f['kind'] == 'pair_equal']
        self.assertGreaterEqual(len(pairs), 5)
        for f in pairs:
            a, b = h.hygiene_record(f['a'], ''), h.hygiene_record(f['b'], '')
            self.assertEqual(a[f['view']], b[f['view']], f['case'])
            self.assertNotEqual(a[f['view']], '', f['case'])
            self.assertEqual(comparison_key(f['a']) == comparison_key(f['b']), f['v1_equal'], f['case'])

    def test_expected_values(self):
        for f in self.fixtures:
            if f['kind'] != 'expect':
                continue
            name, address = (f['raw'], '') if f['field'] == 'name' else ('', f['raw'])
            record = h.hygiene_record(name, address)
            for key, expected in f['expect'].items():
                self.assertEqual(record[key], expected, f"{f['case']} [{f['id']}] {key}")

    def test_token_counts_hand_counted(self):
        for f in self.fixtures:
            if f['kind'] != 'tokens':
                continue
            record = h.hygiene_record(f['raw'], '')
            self.assertEqual(len(record['name_hyg'].split()), f['expect_tokens']['name_hyg'], f['case'])
            self.assertEqual(len(comparison_key(f['raw']).split()), f['expect_tokens']['v1_name_key'], f['case'])


class RecordContractTests(unittest.TestCase):
    def test_columns_and_types_are_stable(self):
        rec = h.hygiene_record('Acme Ltd', '5 Main Rd')
        self.assertEqual(tuple(rec), h.HYGIENE_COLUMNS)
        for key, value in rec.items():
            self.assertIsNotNone(value, key)
            self.assertIsInstance(value, (str, bool), key)

    def test_empty_inputs_never_produce_none(self):
        rec = h.hygiene_record('', '')
        self.assertEqual(rec['name_hyg'], '')
        self.assertEqual(rec['address_clean'], '')
        self.assertTrue(rec['address_missing'])
        self.assertTrue(all(v is not None for v in rec.values()))

    def test_repair_codes_are_sorted_by_pipeline_order_and_deterministic(self):
        rec = h.hygiene_record('a\x1a‌b  L.L.C.', '')
        self.assertEqual(rec['name_repairs'], 'controls,joiners,dotted,ws')
        self.assertEqual(rec, h.hygiene_record('a\x1a‌b  L.L.C.', ''))

    def test_raw_input_is_never_modified(self):
        raw = 'ಕನ್‌ಸ್ L.L.C.\x1a'
        before = raw
        h.hygiene_record(raw, raw)
        self.assertEqual(raw, before)   # strings are immutable; the point is that no view returns the raw object mutated


class IdempotenceAndPreservationTests(unittest.TestCase):
    STRINGS = ['Bison  L.L.C.', 'École Cœur', 'ಕನ್‌ಸ್ಟ್ರಕ್ಷನ್ಸ್ ಪ್ರೈವೇಟ್', 'N° 5 rue de l’Eglise', 'आदित्य ट्रेडिंग प्रा. लि.',
               'Plot Â\x80\x93 148, Nagar', '  padded  ', 'ＡＢＣ', 'Nº 12, 1º étage', 'Murial STÁR L.L.C.', 'S.A.S', '"ehpad Club SAS']

    def test_every_view_is_idempotent(self):
        for text in self.STRINGS:
            first = h.hygiene_record(text, text)
            for name_view in ['name_hyg', 'name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key']:
                second = h.hygiene_record(first[name_view], '')
                self.assertEqual(second[name_view], first[name_view], f'{name_view} of {text!r}')
            again = h.hygiene_record('', first['address_clean'])
            self.assertEqual(again['address_clean'], first['address_clean'], text)

    def test_marks_and_numbers_are_preserved(self):
        for text in self.STRINGS:
            expected = Counter(c for c in unicodedata.normalize('NFC', text) if unicodedata.category(c)[0] in 'MN')
            rec = h.hygiene_record(text, text)
            got_name = Counter(c for c in rec['name_hyg'] if unicodedata.category(c)[0] in 'MN')
            got_address = Counter(c for c in rec['address_clean'] if unicodedata.category(c)[0] in 'MN')
            for char, count in expected.items():
                self.assertGreaterEqual(got_name[char], count, (text, char))
                self.assertGreaterEqual(got_address[char], count, (text, char))

    def test_digits_are_never_lost_or_changed(self):
        for text in ['5 bis', '5/105', '5-105', 'J 105', '0012', '12A', '224 1/2 48 St', '3-277/1', 'N°5']:
            digits = ''.join(c for c in text if c.isdigit())
            self.assertEqual(''.join(c for c in h.hygiene_record('', text)['address_clean'] if c.isdigit()), digits, text)
            self.assertEqual(''.join(c for c in h.hygiene_record(text, '')['name_hyg'] if c.isdigit()), digits, text)

    def test_hyphenated_numbers_stay_distinct(self):
        clean = lambda t: h.hygiene_record('', t)['address_clean']
        self.assertNotEqual(clean('5-105'), clean('5105'))
        self.assertEqual(clean('5-105'), '5-105')
        self.assertEqual(clean('0012'), '0012')


@unittest.skipUnless((INTERIM / 'test_source1.parquet').exists(), 'data/interim not available')
class RealDataSampleTests(unittest.TestCase):
    """A deterministic 20k-row sample per file: parity with the DuckDB-computed v1 keys and the core invariants."""

    @classmethod
    def setUpClass(cls):
        import duckdb
        con = duckdb.connect()
        con.execute("SET memory_limit='2GB'")
        cls.rows = []
        for table in ['train_source1', 'train_source2', 'train_source3', 'test_source1', 'test_source2', 'test_source3']:
            cls.rows += con.execute(f"""SELECT '{table}', entity_id, business_name, business_address, name_key, address_key
                FROM read_parquet('{(INTERIM / (table + '.parquet')).as_posix()}') WHERE hash(entity_id) % 240 = 0""").fetchall()
        con.close()

    def test_sample_is_large_enough(self):
        self.assertGreater(len(self.rows), 90_000)

    def test_lmn_key_equals_stored_v1_keys(self):
        for table, eid, name, address, name_key, address_key in self.rows:
            self.assertEqual(h.lmn_key(name), name_key, (table, eid))
            self.assertEqual(h.lmn_key(address), address_key, (table, eid))

    def test_no_new_empty_names_and_missing_matches_v1(self):
        for table, eid, name, address, name_key, address_key in self.rows:
            rec = h.hygiene_record(name, address)
            self.assertNotEqual(rec['name_hyg'], '', (table, eid))
            self.assertEqual(rec['address_missing'], address.strip() == '', (table, eid))
            if address_key:
                self.assertNotEqual(h.lmn_key(rec['address_clean']), '', (table, eid))

    def test_hygiene_never_loses_marks_or_numbers_on_real_rows(self):
        for table, eid, name, address, _nk, _ak in self.rows:
            rec = h.hygiene_record(name, address)
            for raw, view in [(name, rec['name_hyg']), (address, rec['address_clean'])]:
                expected = Counter(c for c in unicodedata.normalize('NFC', raw) if unicodedata.category(c)[0] in 'MN')
                got = Counter(c for c in view if unicodedata.category(c)[0] in 'MN')
                for char, count in expected.items():
                    self.assertGreaterEqual(got[char], count, (table, eid, char))

    def test_views_are_idempotent_on_real_rows(self):
        for table, eid, name, address, _nk, _ak in self.rows[::7]:
            first = h.hygiene_record(name, address)
            second = h.hygiene_record(first['name_hyg'], first['address_clean'])
            self.assertEqual(second['name_hyg'], first['name_hyg'], (table, eid))
            self.assertEqual(second['address_clean'], first['address_clean'], (table, eid))


if __name__ == '__main__':
    unittest.main()
