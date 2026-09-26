"""Unicode hygiene primitives (hyg_v2_0).

Raw text is never modified in place: every function returns a new string. Repairs are deliberately narrow and
each one is justified by a measured pattern in the supplied data (see reports/eda/cleaning_decisions.md):

* control / C1 characters and the corrupted-dash mojibake become a separator (A-01);
* ZWNJ / ZWJ are deleted, not spaced, so an Indic word stays one token (N-12);
* dotted legal acronyms are joined only when the joined form is in the lexicon (N-03);
* curly apostrophes, dash variants and ``N°`` / ``Nº`` before a number are normalised (A-09);
* Latin accent marks are folded only on Latin bases, so Indic marks survive (N-05).

``lmn_key`` is the frozen v1 rule (letters, marks and numbers survive; everything else is a boundary) and must stay
identical to ``scripts/normalization.comparison_key``.
"""
import re
import unicodedata
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from .lexicons import legal_dotted

# --------------------------------------------------------------------------------------------- patterns
# Control characters (Cc) other than TAB/LF/CR, optionally preceded by the lead character of the observed corrupted
# dash (A-circumflex / a-circumflex / A-tilde) but only when that lead is followed by a C1 control.
_CONTROL_SEPARATOR = re.compile(r'(?:[ÂâÃ](?=[\x80-\x9f]))?[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]+')
_MOJIBAKE_CHAR = re.compile(r'[\x80-\x9f\x1a]')          # C1 controls and SUB (the observed dash corruption)
_MULTISPACE = re.compile(r'\s{2,}', re.ASCII)            # ASCII whitespace only, same meaning as the audit's SQL
_JOINERS = str.maketrans('', '', '‌‍')
_APOSTROPHES = str.maketrans({'‘': "'", '’': "'", '‛': "'"})
_DASHES = str.maketrans({c: '-' for c in '‐‑‒–—―−'})
_ORDINAL_NO = re.compile(r'(?<!\w)([Nn])\s?[°º]\s?(?=\d)')   # N°5, N° 5, Nº 5  ->  No 5
_ORDINAL_MASC = str.maketrans({'º': '°'})                   # remaining º behaves like °, as it does in v1 terms
_DOTTED_ACRONYM = re.compile(r'(?<![A-Za-z])(?<![A-Za-z]\.)[A-Za-z](?:\.[A-Za-z])+\.?(?![A-Za-z])')  # starts at a token boundary
LIGATURES = str.maketrans({'œ': 'oe', 'Œ': 'OE', 'æ': 'ae', 'Æ': 'AE', 'ß': 'ss',
                           'ø': 'o', 'Ø': 'O', 'ł': 'l', 'Ł': 'L', 'đ': 'd', 'Đ': 'D'})

_ASCII_KEY_TABLE = {c: (chr(c).lower() if chr(c).isalnum() else ' ') for c in range(128)}
_KEEP: Dict[str, bool] = {}
_CATEGORY: Dict[str, str] = {}


# --------------------------------------------------------------------------------------------- v1 key
def _category(char: str) -> str:
    try:
        return _CATEGORY[char]
    except KeyError:
        value = _CATEGORY[char] = unicodedata.category(char)
        return value


def _keep(char: str) -> bool:
    try:
        return _KEEP[char]
    except KeyError:
        value = _KEEP[char] = unicodedata.category(char)[0] in 'LMN'
        return value


def lmn_key(value: str) -> str:
    """The frozen v1 rule: NFC, lower-case, keep Unicode letters/marks/numbers, other runs become one space."""
    if value.isascii():
        return ' '.join(value.translate(_ASCII_KEY_TABLE).split())
    value = unicodedata.normalize('NFC', value).lower()
    return ' '.join(''.join(c if _keep(c) else ' ' for c in value).split())


# --------------------------------------------------------------------------------------------- primitives
def nfc(value: str) -> str:
    return unicodedata.normalize('NFC', value)


def remove_joiners(value: str) -> str:
    """Delete U+200C / U+200D (no replacement) so an Indic word is not split into two tokens."""
    return value.translate(_JOINERS)


def fold_latin(value: str) -> str:
    """Strip combining marks whose base is a Latin letter, then fold ligatures. Indic marks are untouched."""
    if value.isascii():
        return value
    out: List[str] = []
    latin_base = False
    for char in unicodedata.normalize('NFD', value):
        if unicodedata.category(char)[0] == 'M':
            if not latin_base:
                out.append(char)
        else:
            latin_base = ord(char) < 0x250 and char.isalpha()
            out.append(char)
    return unicodedata.normalize('NFC', ''.join(out)).translate(LIGATURES)


def repair_controls(value: str) -> str:
    """Replace control characters and the corrupted-dash mojibake by a single space (raw text is kept elsewhere)."""
    return _CONTROL_SEPARATOR.sub(' ', value)


def normalize_punctuation(value: str) -> str:
    """Curly apostrophes -> ', dash variants -> -, ``N°5`` -> ``No 5``, remaining º -> °."""
    value = value.translate(_APOSTROPHES).translate(_DASHES)
    value = _ORDINAL_NO.sub(lambda m: m.group(1) + 'o ', value)
    return value.translate(_ORDINAL_MASC)


def join_apostrophes(value: str) -> str:
    """Optional view: delete apostrophes (L'Eglise -> LEglise, Women's -> Womens). The split view is the default."""
    return value.translate(_APOSTROPHES).replace("'", '')


def collapse_ws(value: str) -> str:
    return ' '.join(value.split())


def join_dotted_legal(value: str, dotted: Optional[FrozenSet[str]] = None) -> str:
    """Collapse ``L.L.C.`` -> ``LLC`` only when the joined form is in the dotted lexicon; initials stay untouched."""
    lexicon = legal_dotted() if dotted is None else dotted

    def replace(match):
        joined = match.group(0).replace('.', '')
        return joined if joined.lower() in lexicon else match.group(0)

    return _DOTTED_ACRONYM.sub(replace, value)


# --------------------------------------------------------------------------------------------- flags
def has_control(value: str) -> bool:
    """Any Cc character. A string of only printable characters cannot contain one, which makes the common case cheap."""
    return (not value.isprintable()) and any(_category(c) == 'Cc' for c in value)


def has_format(value: str) -> bool:
    """Any Cf character (ZWNJ, soft hyphen, BOM, ...). ASCII has none."""
    return (not value.isascii()) and any(_category(c) == 'Cf' for c in value)


def has_mojibake(value: str) -> bool:
    return _MOJIBAKE_CHAR.search(value) is not None


def has_multispace(value: str) -> bool:
    return _MULTISPACE.search(value) is not None


def text_flags(value: str) -> Dict[str, bool]:
    return {'has_control': has_control(value), 'has_format': has_format(value),
            'mojibake': has_mojibake(value), 'multispace': has_multispace(value)}


# --------------------------------------------------------------------------------------------- pipelines
def clean_text(value: str, *, dotted: Optional[FrozenSet[str]] = None, join_legal_acronyms: bool = False
               ) -> Tuple[str, Tuple[str, ...]]:
    """Case- and punctuation-preserving hygiene. Returns (text, repair codes that changed the string).

    Order: NFC, controls/mojibake, joiners, punctuation, dotted legal acronyms (names only), whitespace.
    """
    repairs: List[str] = []
    text = value

    def step(code: str, new: str) -> str:
        if new != text:
            repairs.append(code)
        return new

    text = step('nfc', nfc(text))
    text = step('controls', repair_controls(text))
    text = step('joiners', remove_joiners(text))
    text = step('punct', normalize_punctuation(text))
    if join_legal_acronyms:
        text = step('dotted', join_dotted_legal(text, dotted))
    text = step('ws', collapse_ws(text))
    return text, tuple(repairs)


def name_hygiene(name: str, dotted: Optional[FrozenSet[str]] = None) -> Tuple[Dict[str, object], str]:
    """Name views and flags, plus the case-preserving cleaned text (reused by the name features so it is computed once)."""
    cleaned, repairs = clean_text(name, dotted=dotted, join_legal_acronyms=True)
    record: Dict[str, object] = {
        'name_hyg': lmn_key(cleaned),
        'name_latin_accent_key': lmn_key(fold_latin(nfc(name))),
        'name_joiner_key': lmn_key(remove_joiners(name)),
        'name_compat_key': lmn_key(unicodedata.normalize('NFKC', name)),
        'name_apos_join_key': lmn_key(join_apostrophes(cleaned)),
        'name_repairs': ','.join(repairs),
    }
    for key, value in text_flags(name).items():
        record[f'name_{key}'] = value
    return record, cleaned


def address_hygiene(address: str) -> Tuple[Dict[str, object], str]:
    """Address text view and flags, plus the cleaned text (same string as ``address_clean``)."""
    cleaned, repairs = clean_text(address)
    record: Dict[str, object] = {'address_clean': cleaned, 'address_missing': address.strip() == '', 'address_repairs': ','.join(repairs)}
    for key, value in text_flags(address).items():
        record[f'address_{key}'] = value
    return record, cleaned


def hygiene_record(name: str, address: str, dotted: Optional[FrozenSet[str]] = None) -> Dict[str, object]:
    """All Phase 2 columns for one record. Strings are never None; empty means empty."""
    record, _ = name_hygiene(name, dotted)
    address_record, _ = address_hygiene(address)
    record.update(address_record)
    return {key: record[key] for key in HYGIENE_COLUMNS}


HYGIENE_COLUMNS: Tuple[str, ...] = (
    'name_hyg', 'name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key', 'name_repairs',
    'name_has_control', 'name_has_format', 'name_mojibake', 'name_multispace',
    'address_clean', 'address_missing', 'address_repairs',
    'address_has_control', 'address_has_format', 'address_mojibake', 'address_multispace',
)
