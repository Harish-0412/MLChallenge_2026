"""Lexicon loading and validation. Lexicons are plain TSV files under src/cleaning/lexicon_data/ and are hashed into the manifest.

Legal forms are country-scoped (a token such as ``private`` or ``sci`` is an ordinary word outside the country whose
tier lists it). ``legal_index(country)`` is ``generic`` + the country's tier + the script-specific ``native`` tier;
an unknown country therefore gets only ``generic`` + ``native``, so a new country never breaks the build.
"""
import csv
import hashlib
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

LEXICON_DIR = Path(__file__).resolve().parent / 'lexicon_data'
LEGAL_TIERS = ('generic', 'US', 'IN', 'FR', 'native')


class LexiconError(ValueError):
    pass


def read_lexicon(name: str) -> List[Dict[str, str]]:
    """Read a tab-separated lexicon with a header row. No quoting: lexicon cells never contain tabs or newlines."""
    path = LEXICON_DIR / name
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t', quoting=csv.QUOTE_NONE))


def lexicon_sha256(name: str) -> str:
    return hashlib.sha256((LEXICON_DIR / name).read_bytes()).hexdigest()


def all_lexicon_hashes() -> Dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(LEXICON_DIR.glob('*.tsv'))}


@lru_cache(maxsize=None)
def legal_dotted() -> FrozenSet[str]:
    """Joined forms of dotted acronyms that may be collapsed (L.L.C. -> LLC). Lower-case."""
    return frozenset(row['collapsed'].lower() for row in read_lexicon('legal_dotted.tsv'))


# ------------------------------------------------------------------------------------------ legal forms
@lru_cache(maxsize=None)
def _legal_rows() -> Tuple[Tuple[str, str, str, int], ...]:
    rows = []
    seen = set()
    code_by_token: Dict[str, str] = {}
    for row in read_lexicon('legal_forms.tsv'):
        tier, token, code, rank = row['tier'], row['token'], row['code'], int(row['rank'])
        if tier not in LEGAL_TIERS:
            raise LexiconError(f'legal_forms.tsv: unknown tier {tier!r}')
        if token != token.lower() or not token or ' ' in token:
            raise LexiconError(f'legal_forms.tsv: token {token!r} must be one lower-case token')
        if unicodedata.normalize('NFC', token) != token:
            raise LexiconError(f'legal_forms.tsv: token {token!r} is not NFC-normalised')
        if (tier, token) in seen:
            raise LexiconError(f'legal_forms.tsv: duplicate ({tier}, {token})')
        seen.add((tier, token))
        if code_by_token.setdefault(token, code) != code:
            raise LexiconError(f'legal_forms.tsv: token {token!r} maps to two codes')
        rows.append((tier, token, code, rank))
    rank_of: Dict[str, int] = {}
    for _tier, _token, code, rank in rows:
        if rank_of.setdefault(code, rank) != rank:
            raise LexiconError(f'legal_forms.tsv: code {code!r} has two ranks')
    return tuple(rows)


@lru_cache(maxsize=None)
def legal_index_for_tier(tier: Optional[str]) -> Dict[str, Tuple[str, int]]:
    active = {'generic', 'native'} | ({tier} if tier else set())
    return {token: (code, rank) for t, token, code, rank in _legal_rows() if t in active}


def country_tier(country: str) -> Optional[str]:
    return _country_tiers().get(country)


@lru_cache(maxsize=None)
def _country_tiers() -> Dict[str, str]:
    mapping = {r['country']: r['tier'] for r in read_lexicon('country_tiers.tsv')}
    bad = {t for t in mapping.values() if t not in LEGAL_TIERS}
    if bad:
        raise LexiconError(f'country_tiers.tsv: unknown tiers {bad}')
    return mapping


def legal_index(country: str) -> Dict[str, Tuple[str, int]]:
    """token -> (canonical code, rank) active for this country."""
    return legal_index_for_tier(country_tier(country))


# ------------------------------------------------------------------------------------------ other name lexicons
@lru_cache(maxsize=None)
def noise_tokens(kind: str) -> FrozenSet[str]:
    """kind: ``leading`` token removed only at the start of the core; ``connector`` token removed anywhere;
    ``leading_pattern`` enables a raw-text pattern implemented in names.py (currently ``m/s``)."""
    rows = read_lexicon('name_noise_tokens.tsv')
    unknown = {r['kind'] for r in rows} - {'leading', 'connector', 'leading_pattern'}
    if unknown:
        raise LexiconError(f'name_noise_tokens.tsv: unknown kinds {unknown}')
    return frozenset(r['token'] for r in rows if r['kind'] == kind)


@lru_cache(maxsize=None)
def generic_tokens(country: str) -> FrozenSet[str]:
    return frozenset(r['token'] for r in read_lexicon('generic_tokens.tsv') if r['country'] == country)


@lru_cache(maxsize=None)
def appended_noise(country: str) -> FrozenSet[str]:
    """Trailing filler words far more frequent in S2/S3 than in the clean reference S1 (unlabeled lift), per country."""
    return frozenset(r['token'] for r in read_lexicon('appended_noise.tsv') if r['country'] == country)


@lru_cache(maxsize=None)
def placeholder_names() -> FrozenSet[str]:
    return frozenset(r['token'] for r in read_lexicon('placeholders.tsv'))


# ------------------------------------------------------------------------------------------ address lexicons
STATE_KINDS = ('code', 'name', 'native', 'alias', 'department')
ABBREV_RULES = ('any', 'suffix', 'suffix_multi')
TIER_OF = {'US': 'US', 'India': 'IN', 'France': 'FR'}


@lru_cache(maxsize=None)
def state_forms(country: str) -> Dict[str, Tuple[str, str]]:
    """form -> (canonical region, kind) for one country. Forms are lower-case NFC tokens joined by single spaces."""
    rows = read_lexicon('states.tsv')
    seen = set()
    names = {(r['country'], r['canonical']) for r in rows if r['kind'] == 'name'}
    for r in rows:
        if r['kind'] not in STATE_KINDS:
            raise LexiconError(f"states.tsv: unknown kind {r['kind']!r}")
        if unicodedata.normalize('NFC', r['form']) != r['form'] or r['form'] != r['form'].lower():
            raise LexiconError(f"states.tsv: form {r['form']!r} must be lower-case NFC")
        if (r['country'], r['form']) in seen:
            raise LexiconError(f"states.tsv: duplicate ({r['country']}, {r['form']})")
        seen.add((r['country'], r['form']))
        if (r['country'], r['canonical']) not in names:
            raise LexiconError(f"states.tsv: canonical {r['canonical']!r} of {r['form']!r} has no 'name' row")
    return {r['form']: (r['canonical'], r['kind']) for r in rows if r['country'] == country}


@lru_cache(maxsize=None)
def state_canonicals(country: str) -> FrozenSet[str]:
    return frozenset(c for c, _k in state_forms(country).values())


@lru_cache(maxsize=None)
def address_abbrev(country: str) -> Dict[str, Tuple[str, str]]:
    """abbreviation -> (expansion, rule) for the country's tier. Unknown countries have none."""
    tier = TIER_OF.get(country)
    out = {}
    for r in read_lexicon('address_abbrev.tsv'):
        if r['rule'] not in ABBREV_RULES:
            raise LexiconError(f"address_abbrev.tsv: unknown rule {r['rule']!r}")
        if r['tier'] == tier:
            out[r['abbr']] = (r['expansion'], r['rule'])
    return out


NOISE_KINDS = ('placeholder_segment', 'noise_token', 'noise_token_number', 'noise_segment_word', 'noise_pattern')


def _noise(kind: str, country: str) -> FrozenSet[str]:
    out = set()
    for r in read_lexicon('address_noise.tsv'):
        if r['kind'] not in NOISE_KINDS:
            raise LexiconError(f"address_noise.tsv: unknown kind {r['kind']!r}")
        if r['kind'] == kind and r['scope'] in ('all', country):
            out.add(r['token'])
    return frozenset(out)


@lru_cache(maxsize=None)
def address_placeholder_segments(country: str = '') -> FrozenSet[str]:
    """Whole comma segments that are junk (``null``, ``n a``, India: ``divreportingcircle``). Unknown country: the ``all`` scope only."""
    return _noise('placeholder_segment', country)


@lru_cache(maxsize=None)
def address_noise_tokens(country: str) -> FrozenSet[str]:
    return _noise('noise_token', country)


@lru_cache(maxsize=None)
def address_noise_number_tokens(country: str) -> FrozenSet[str]:
    """Tokens removed together with a following all-digit token, and only when one follows (India: ``HN 337``)."""
    return _noise('noise_token_number', country)


@lru_cache(maxsize=None)
def address_noise_segment_words(country: str) -> FrozenSet[str]:
    """A comma segment containing one of these tokens is removed whole (India: ``Pune Region``)."""
    return _noise('noise_segment_word', country)


@lru_cache(maxsize=None)
def address_noise_patterns(country: str) -> FrozenSet[str]:
    return _noise('noise_pattern', country)
