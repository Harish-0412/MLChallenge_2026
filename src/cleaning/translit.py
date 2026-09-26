"""Phase 4: script census and Latin bridging views (feat_v2_0).

* ``script_mask`` / ``script_names``: which scripts a string uses. Script is NOT language: Devanagari is used for several
  languages, so no column is ever called "language". The nine Indic scripts of the census are separate bits.
* ``to_ascii`` / ``name_translit``: an *auxiliary* Latin view. The raw field is never transliterated in place.
* ``skeleton``: a phonetic skeleton applied identically to BOTH sides (the Latin reference name and the transliterated
  native-script name). It removes vowels, so it collides more than any other view: it is a retrieval/feature view for
  cross-script pairs and never a key on its own (see reports/cleaning/translit_bakeoff.md for the measured trade-off).

The engine and skeleton variant below are the outcome of the bake-off in scripts/translit_bakeoff.py.
"""
import re
import unicodedata
from bisect import bisect_right
from typing import Dict, List

from anyascii import anyascii

from .script_ranges import SCRIPT_RANGES

# Bake-off (27,230 India cross-script true pairs, provisional 5% sample; reports/cleaning/translit_bakeoff.md): once the coarse skeleton is used all
# engines tie (>=80 similarity for 93.6-93.9%, HK 90.8%), so the fastest, dependency-light ISC engine wins. The coarse skeleton lifts the share of
# pairs with similarity >= 80 from 67.7% to 93.6% at similar ambiguity (median 60 vs 57 S1 names per exact key).
DEFAULT_ENGINE = 'anyascii'
DEFAULT_SKELETON_COARSE = True

SCRIPT_BITS: Dict[str, int] = {'Latin': 1 << 0, 'Devanagari': 1 << 1, 'Bengali': 1 << 2, 'Gurmukhi': 1 << 3, 'Gujarati': 1 << 4,
                               'Oriya': 1 << 5, 'Tamil': 1 << 6, 'Telugu': 1 << 7, 'Kannada': 1 << 8, 'Malayalam': 1 << 9, 'Other': 1 << 10}
INDIC_SCRIPTS = ('Devanagari', 'Bengali', 'Gurmukhi', 'Gujarati', 'Oriya', 'Tamil', 'Telugu', 'Kannada', 'Malayalam')
_LATIN, _OTHER = SCRIPT_BITS['Latin'], SCRIPT_BITS['Other']

_INTERVALS = sorted((a, b, SCRIPT_BITS.get(script, _OTHER)) for script, ranges in SCRIPT_RANGES.items() for a, b in ranges)
_STARTS = [a for a, _b, _bit in _INTERVALS]
_ASCII_LETTER = re.compile(r'[A-Za-z]')
_BIT_CACHE: Dict[str, int] = {}


def _char_bit(char: str) -> int:
    try:
        return _BIT_CACHE[char]
    except KeyError:
        pass
    code = ord(char)
    index = bisect_right(_STARTS, code) - 1
    if index >= 0 and code <= _INTERVALS[index][1]:
        bit = _INTERVALS[index][2]
    elif char.isalpha():
        bit = _LATIN if unicodedata.name(char, '').startswith('LATIN') else _OTHER
    else:
        bit = 0
    _BIT_CACHE[char] = bit
    return bit


def script_mask(text: str) -> int:
    """Bitmask of the scripts of the letters, marks and digits in ``text`` (punctuation and spaces contribute nothing)."""
    if text.isascii():
        return _LATIN if _ASCII_LETTER.search(text) else 0
    mask = 0
    for char in text:
        mask |= _char_bit(char)
    return mask


def script_names(mask: int) -> List[str]:
    return [name for name, bit in SCRIPT_BITS.items() if mask & bit]


def has_indic(mask: int) -> bool:
    return any(mask & SCRIPT_BITS[s] for s in INDIC_SCRIPTS)


# ------------------------------------------------------------------------------------------ transliteration
_ANUSVARA = str.maketrans({'ं': 'n', 'ং': 'n', 'ਂ': 'n', 'ં': 'n', 'ଂ': 'n', 'ஂ': 'n',
                           'ం': 'n', 'ಂ': 'n', 'ം': 'n'})


def to_ascii(text: str, engine: str = DEFAULT_ENGINE) -> str:
    """ASCII rendering of ``text``. ``anyascii`` is character-level (no dictionary, no network); ``anyascii_n`` first maps
    the anusvara sign to ``n`` (anyascii renders it ``m``, which disagrees with Latin spellings such as ``Engineering``)."""
    if text.isascii():
        return text
    if engine == 'anyascii_n':
        text = text.translate(_ANUSVARA)
    elif engine != 'anyascii':
        raise ValueError(f'unknown engine {engine!r}')
    return anyascii(text)


def name_translit(cleaned: str, engine: str = DEFAULT_ENGINE) -> str:
    """Lower-case, boundary-normalised ASCII tokens. Latin accents and ligatures fold as well (a side effect of ASCII output)."""
    from .text_hygiene import lmn_key
    return lmn_key(to_ascii(cleaned, engine))


# ------------------------------------------------------------------------------------------ skeleton
_DIGRAPHS = (('ph', 'f'), ('sh', 's'), ('ch', 'c'), ('kh', 'k'), ('gh', 'g'), ('th', 't'), ('dh', 'd'), ('bh', 'b'), ('jh', 'j'))
_LETTER_MAP = str.maketrans({'w': 'v', 'z': 'j', 'q': 'k', 'y': 'i'})
_VOWELS = re.compile('[aeiou]')
_DOUBLE = re.compile(r'([a-z0-9])\1+')
_COARSE = str.maketrans({'d': 't', 'g': 'k', 'c': 'k', 'b': 'p', 'm': 'n'})   # voicing, c/k and nasal merges (collision-prone)
_KEEP = re.compile(r'[^a-z0-9 ]+')


def _skeleton_pass(word: str, coarse: bool) -> str:
    for a, b in _DIGRAPHS:
        word = word.replace(a, b)
    word = word.translate(_LETTER_MAP).replace('x', 'ks')
    word = _DOUBLE.sub(r'\1', word)
    if word:
        word = word[0] + _VOWELS.sub('', word[1:])
    if coarse:
        word = _DOUBLE.sub(r'\1', word.translate(_COARSE))
    return word


def skeleton_word(word: str, coarse: bool = False) -> str:
    """Apply the skeleton pass until nothing changes. One pass is not enough for a normal form: dropping vowels can create new
    doubled letters and can re-form digraphs (``sahar`` -> ``shr`` -> ``sr``). The length never grows after the first pass
    (only ``x`` -> ``ks`` lengthens and no ``x`` survives), so the loop terminates."""
    while True:
        new = _skeleton_pass(word, coarse)
        if new == word:
            return word
        word = new


def skeleton(ascii_text: str, coarse: bool = DEFAULT_SKELETON_COARSE) -> str:
    """Phonetic skeleton of ASCII text: first letter of each word kept, later vowels dropped, digraphs and doubles folded."""
    words = _KEEP.sub(' ', ascii_text.lower()).split()
    return ' '.join(skeleton_word(w, coarse) for w in words)


def name_skeleton(core: str, engine: str = DEFAULT_ENGINE, coarse: bool = DEFAULT_SKELETON_COARSE) -> str:
    """Skeleton of the transliterated core tokens (legal forms already removed)."""
    return skeleton(to_ascii(core, engine), coarse)
