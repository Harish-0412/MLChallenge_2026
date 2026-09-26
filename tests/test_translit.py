import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import lexicons as L  # noqa: E402
from cleaning import names as N  # noqa: E402
from cleaning import text_hygiene as h  # noqa: E402
from cleaning import translit as T  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'translit_fixtures_v2.jsonl'


class ScriptMaskTests(unittest.TestCase):
    """Characters are hand-picked: the first letter of each block, so the expectations do not depend on the range table."""

    LETTERS = {'Latin': 'a', 'Devanagari': 'अ', 'Bengali': 'অ', 'Gurmukhi': 'ਅ', 'Gujarati': 'અ', 'Oriya': 'ଅ',
               'Tamil': 'அ', 'Telugu': 'అ', 'Kannada': 'ಅ', 'Malayalam': 'അ'}

    def test_each_script_gets_its_own_bit(self):
        bits = set()
        for name, char in self.LETTERS.items():
            mask = T.script_mask(char)
            self.assertEqual(mask, T.SCRIPT_BITS[name], name)
            self.assertEqual(T.script_names(mask), [name])
            bits.add(mask)
        self.assertEqual(len(bits), 10)

    def test_other_scripts_and_non_letters(self):
        for char in ['ا', 'Я', '漢', 'α']:             # Arabic, Cyrillic, Han, Greek
            self.assertEqual(T.script_mask(char), T.SCRIPT_BITS['Other'], repr(char))
        for text in ['', '  ', '5', ',.-/', '।', '’']:            # digits, punctuation, danda are not letters of a script
            self.assertEqual(T.script_mask(text), 0, repr(text))
        self.assertEqual(T.script_mask('१'), T.SCRIPT_BITS['Devanagari'])   # Devanagari digit belongs to the script

    def test_latin_accents_and_ligatures_are_latin(self):
        for text in ['é', 'œ', 'ß', 'ł', 'Frédération']:
            self.assertEqual(T.script_mask(text), T.SCRIPT_BITS['Latin'], repr(text))
        # regression: the ordinal indicators are Script=Latin although their names do not start with LATIN. They occur in
        # 23,690 French addresses (Nº 5) and were first misclassified as "Other" by a name-based fallback.
        for text in ['º', 'ª', 'Nº 5', 'ᵃ', 'Ａ']:
            self.assertEqual(T.script_mask(text), T.SCRIPT_BITS['Latin'], repr(text))
        self.assertEqual(T.script_mask('é'), T.SCRIPT_BITS['Latin'])         # combining accent contributes nothing

    def test_mixed_scripts_and_marks(self):
        mask = T.script_mask('Foo अ অ')
        self.assertEqual(T.script_names(mask), ['Latin', 'Devanagari', 'Bengali'])
        self.assertEqual(T.script_mask('का'), T.SCRIPT_BITS['Devanagari'])   # consonant + vowel sign (mark)
        self.assertTrue(T.has_indic(mask))
        self.assertFalse(T.has_indic(T.script_mask('Foo')))

    def test_ascii_fast_path_agrees_with_generic_path(self):
        rng = random.Random(3)
        for _ in range(2000):
            text = ''.join(rng.choice('abcXYZ 019,.-éअ') for _ in range(rng.randint(0, 12)))
            slow = 0
            for char in text:
                slow |= T._char_bit(char)
            self.assertEqual(T.script_mask(text), slow, repr(text))


class TranslitAndSkeletonTests(unittest.TestCase):
    def test_to_ascii(self):
        self.assertEqual(T.to_ascii('Café Cœur'), 'Cafe Coeur')
        self.assertEqual(T.to_ascii('plain'), 'plain')
        for text in ['आदित्य', 'ಕನ್ಸ್', 'அக்']:
            out = T.to_ascii(text)
            self.assertTrue(out.isascii() and out, text)
        with self.assertRaises(ValueError):
            T.to_ascii('अ', 'nope')

    def test_anusvara_variant_differs_only_on_anusvara(self):
        text = 'इंजीनियरिंग'      # Devanagari 'engineering' with two anusvaras
        plain, with_n = T.to_ascii(text, 'anyascii'), T.to_ascii(text, 'anyascii_n')
        self.assertNotEqual(plain, with_n)
        self.assertEqual(plain.count('m') - with_n.count('m'), 2)
        self.assertEqual(T.to_ascii('का', 'anyascii_n'), T.to_ascii('का', 'anyascii'))

    def test_skeleton_hand_derived(self):
        base = lambda s: T.skeleton(s, coarse=False)
        self.assertEqual(base('private limited'), 'prvt lmtd')
        self.assertEqual(base('praivet'), 'prvt')
        self.assertEqual(base('philip'), 'flp')
        self.assertEqual(base('Shri'), 'sr')
        self.assertEqual(base('Bhatt'), 'bt')
        self.assertEqual(base('Wisdom'), 'vsdm')
        self.assertEqual(base('xerox'), 'ksrks')
        self.assertEqual(base('Trading 24'), 'trdng 24')
        self.assertEqual(base('  a--b '), 'a b')

    def test_coarse_merges_voicing_and_nasals(self):
        self.assertEqual(T.skeleton('limited', coarse=True), 'lnt')
        self.assertEqual(T.skeleton('limitet', coarse=True), 'lnt')              # Tamil-style unvoiced d
        self.assertEqual(T.skeleton('technology', coarse=True), T.skeleton('teknology', coarse=True))
        self.assertNotEqual(T.skeleton('limited', False), T.skeleton('limitet', False))

    def test_skeleton_is_idempotent_and_ascii(self):
        rng = random.Random(4)
        alphabet = 'abcdefghijklmnopqrstuvwxyz  01'
        for coarse in (False, True):
            for _ in range(3000):
                text = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
                once = T.skeleton(text, coarse)
                self.assertEqual(T.skeleton(once, coarse), once, (text, coarse))
                self.assertTrue(once.isascii())

    def test_defaults_come_from_the_bakeoff(self):
        self.assertEqual(T.DEFAULT_ENGINE, 'anyascii')
        self.assertTrue(T.DEFAULT_SKELETON_COARSE)
        self.assertEqual(T.skeleton('limited'), 'lnt')


class NativeLegalLexiconTests(unittest.TestCase):
    def test_native_tier_is_country_agnostic_nfc_and_disjoint_from_latin(self):
        rows = [r for r in L._legal_rows() if r[0] == 'native']
        self.assertEqual(len(rows), 33)
        latin = {t for tier, t, _c, _r in L._legal_rows() if tier != 'native'}
        for _tier, token, code, _rank in rows:
            self.assertIn(token, L.legal_index('Atlantis'))                    # active for an unknown country
            self.assertFalse(token.isascii(), token)
            self.assertNotIn(token, latin)
            self.assertIn(code, {'LTD', 'PVT', 'LLP'})
        self.assertEqual({T.script_names(T.script_mask(t))[0] for _tier, t, _c, _r in rows}, set(T.INDIC_SCRIPTS))

    def test_each_script_has_limited_private_and_llp(self):
        by_script = {}
        for _tier, token, code, _rank in (r for r in L._legal_rows() if r[0] == 'native'):
            by_script.setdefault(T.script_names(T.script_mask(token))[0], set()).add(code)
        for script in T.INDIC_SCRIPTS:
            self.assertEqual(by_script[script], {'LTD', 'PVT', 'LLP'}, script)


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = [json.loads(l) for l in FIXTURES.read_text(encoding='utf-8').splitlines() if l.strip()]

    def test_shape(self):
        self.assertEqual(len(self.fixtures), 31)
        self.assertEqual(sum(f['kind'] == 'legal_pair' for f in self.fixtures), 27)
        self.assertEqual({f['script'] for f in self.fixtures if f['kind'] == 'legal_pair'}, set(T.INDIC_SCRIPTS))

    def test_native_legal_form_agrees_with_the_latin_reference_of_a_true_pair(self):
        """27 real pairs (3 legal forms x 9 scripts): S1 states the form in Latin, the native target must map to the same code."""
        for f in (x for x in self.fixtures if x['kind'] == 'legal_pair'):
            s1 = N.build_name_features(f['s1'], 'India')
            target = N.build_name_features(f['target'], 'India')
            self.assertEqual(s1['legal_form'], f['expect_legal_form'], f"{f['case']}: reference {f['s1']!r}")
            self.assertEqual(target['legal_form'], f['expect_legal_form'], f"{f['case']} {f['ids']}: {f['target']!r} -> {target['name_core']!r}")
            self.assertEqual(target['legal_form_pos'], 'suffix', f['case'])
            self.assertTrue(T.has_indic(target['name_scripts']), f['case'])
            self.assertLess(target['name_ncore'], target['name_ntokens'], f['case'])

    def test_skeleton_pairs_are_equal_by_hand_derivation(self):
        for f in (x for x in self.fixtures if x['kind'] == 'skeleton_pair'):
            a = N.build_name_features(f['s1'], 'India')
            b = N.build_name_features(f['target'], 'India')
            self.assertEqual(T.skeleton(T.to_ascii(a['name_core']), coarse=False), T.skeleton(T.to_ascii(b['name_core']), coarse=False), f['case'])
            self.assertEqual(a['name_skeleton'], b['name_skeleton'], f['case'])
        smart = next(x for x in self.fixtures if x['case'] == 'devanagari_smart_builders')
        self.assertEqual(N.build_name_features(smart['s1'], 'India')['name_skeleton'], T.skeleton('smart builders'))
        self.assertEqual(T.skeleton('smart builders', coarse=False), 'smrt bldrs')

    def test_zwnj_names_are_one_token_per_word_and_native_legal_removed(self):
        for f in (x for x in self.fixtures if x['kind'] == 'native_name'):
            record = N.build_name_features(f['raw'], f['country'])
            for key, expected in f['expect'].items():
                self.assertEqual(record[key], expected, f"{f['case']} {key}")
            self.assertEqual(record['name_ntokens'], len(f['raw'].split()), f['case'])   # ZWNJ no longer splits words
            self.assertGreater(len(h.lmn_key(f['raw'].replace('‌', ' ')).split()), record['name_ntokens'])

    def test_devanagari_abbreviated_legal_form_from_the_challenge_statement(self):
        record = N.build_name_features('आदित्य ट्रेडिंग प्रा. लि.', 'India')
        self.assertEqual(record['legal_form'], 'PVT+LTD')
        self.assertEqual(record['name_core'], 'आदित्य ट्रेडिंग')
        self.assertTrue(record['name_translit'].isascii() and record['name_skeleton'].isascii() and record['name_skeleton'])


class RecordViewTests(unittest.TestCase):
    def test_latin_names_pass_through(self):
        record = N.build_name_features('Café Trading Pvt Ltd', 'India')
        self.assertEqual(record['name_scripts'], T.SCRIPT_BITS['Latin'])
        self.assertEqual(record['name_translit'], 'cafe trading pvt ltd')
        self.assertEqual(record['name_skeleton'], T.skeleton('cafe trading'))

    def test_empty_and_non_letter_names(self):
        for raw in ['', '---', '123']:
            record = N.build_name_features(raw, 'US')
            self.assertEqual(record['name_scripts'], 0 if raw != '123' else 0)
            self.assertTrue(record['name_translit'].isascii())
        self.assertEqual(N.build_name_features('', 'US')['name_skeleton'], '')

    def test_translit_is_normalised_and_skeleton_stable(self):
        for raw in ['स्मार्ट बिल्डर्स', 'Star স্টার', 'Frédération du Sud']:
            record = N.build_name_features(raw, 'India')
            self.assertEqual(record['name_translit'], h.lmn_key(record['name_translit']))
            self.assertEqual(T.skeleton(record['name_skeleton']), record['name_skeleton'])


if __name__ == '__main__':
    unittest.main()
