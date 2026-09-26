"""Phase 5: address features (feat_v2_0).

The raw address and ``address_clean`` (Phase 2) are never replaced. The canonical views below remove *cosmetic* variation that the
data shows is injected into S2/S3, without guessing meaning:

* comma segments are kept (components are re-ordered by the noise, so order-insensitive views are provided);
* state/region forms (US codes and names; India's 16 states in English, code, alias and native script; France's regions and the
  observed départements) are mapped to one canonical name, with a confidence label;
* abbreviations are expanded with country-scoped rules (``St`` in the US only at the end of a segment or before a unit, so
  ``St Louis`` stays; French ``St`` is always *saint*);
* injected components (``null`` / ``N/A`` segments, ``CDP``, ``PMB n``, ``PO BOX n``) are removed from the canonical view and reported;
* leading zeros of numbers are stripped in the canonical view only (``05618`` -> ``5618``); raw spans keep them;
* the number labels ``No`` / ``N`` directly before a number are dropped from the canonical view (measured neutral in the US, +1 point in India;
  France carries an injected ``No <n>`` label: 70,725 S2/S3 addresses vs 1 in S1); the spans keep the label as context;
* numbers are extracted as spans with their preceding context and are never given a meaning (house, unit and postal numbers are
  indistinguishable by shape).

Nothing here is a hard filter: missing information is a flag, not a value.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import text_hygiene as h
from . import translit as T
from .lexicons import (address_abbrev, address_noise_number_tokens, address_noise_patterns, address_noise_segment_words, address_noise_tokens,
                       address_placeholder_segments, state_forms)

ADDRESS_COLUMNS: Tuple[str, ...] = (
    'address_canon', 'address_tokset', 'address_segset', 'address_segments', 'address_nsegments',
    'address_numbers_raw', 'address_numbers_canon', 'address_number_ctx', 'address_postal_candidates',
    'address_state_canon', 'address_state_conf', 'address_city_candidates', 'address_scripts',
    'address_null_tokens', 'address_had_leading_zero', 'address_extras', 'address_parse_conf',
)

_UNIT_WORDS = frozenset({'apt', 'apartment', 'suite', 'ste', 'unit', 'fl', 'floor', 'bldg', 'building', 'rm', 'room', 'no', 'number'})
_STREET_WORDS = frozenset({
    'street', 'road', 'drive', 'avenue', 'lane', 'circle', 'place', 'boulevard', 'trail', 'parkway', 'terrace', 'cove', 'court', 'way', 'highway',
    'rue', 'impasse', 'route', 'chemin', 'allee', 'cours', 'quai', 'floor', 'unit', 'suite', 'apartment', 'building', 'plot', 'flat', 'house',
    'shop', 'door', 'sector', 'block', 'phase', 'marg', 'near', 'opposite', 'behind', 'opp'})
# A number span: optional 1-letter prefix (J 105, C-251, G2) or 2-letter prefix with hyphen (Rz-99), digits with - / separators,
# an optional trailing letter (12A) or French suffix (5 bis). Ordinals such as 1St / 4th are not spans (the lookahead rejects them).
_NUM_SPAN = re.compile(r'(?<![\w])(?:[A-Za-z][ -]?|[A-Za-z]{2}-)?\d+(?:[-/]\d+)*[A-Za-z]?(?:\s(?i:bis|ter|quater)(?![\w]))?(?![\w])')
_LEADING_ZERO = re.compile(r'(?<!\d)0\d+')
_POSTAL = re.compile(r'(?<!\d)(?:\d{5}|\d{6})(?!\d)')
_ZERO_RUN = re.compile(r'(?<!\d)0+(?=\d)')
_LETTER_HYPHEN_DIGIT = re.compile(r'^([a-z]{1,2})-(?=\d)')
_TAKES_NUMBER = frozenset({'pmb'})
_LABEL_TOKENS = ('no',)          # ``n`` was tried and dropped: no measurable gain on true pairs, and it deletes real unit letters (``Apartment N``)
_KIND_RANK = {'name': 0, 'code': 1, 'alias': 1, 'native': 2, 'department': 3}
_KIND_CONF = {'name': 'exact', 'code': 'alias', 'alias': 'alias', 'native': 'mapped_native', 'department': 'mapped_department'}


def _tokens(text: str) -> List[str]:
    return h.lmn_key(h.fold_latin(text)).split()


def _strip_zeros(token: str) -> str:
    """Strip leading zeros of every digit run: ``00936`` -> ``936``, ``g02`` -> ``g2``, ``0`` stays ``0``."""
    return _ZERO_RUN.sub('', token) if any(c.isdigit() for c in token) else token


def canon_number(span: str) -> str:
    """Lower-case, spaces removed, ``C-251`` -> ``c251``, leading zeros of every digit run stripped (``0012`` -> ``12``)."""
    text = span.lower().replace(' ', '')
    text = _LETTER_HYPHEN_DIGIT.sub(r'\1', text)
    return _ZERO_RUN.sub('', text)


def _remove_noise(tokens: List[str], country: str) -> Tuple[List[str], List[str]]:
    """Remove injected components; repeated until nothing more matches (``HN HN 5 6`` -> ``HN 6`` -> ``''``), so the view is a fixed point."""
    removed: List[str] = []
    while True:
        tokens, found = _remove_noise_once(tokens, country)
        if not found:
            return tokens, removed
        removed += found


def _remove_noise_once(tokens: List[str], country: str) -> Tuple[List[str], List[str]]:
    noise, patterns = address_noise_tokens(country), address_noise_patterns(country)
    number_tokens, segment_words = address_noise_number_tokens(country), address_noise_segment_words(country)
    if tokens and segment_words.intersection(tokens):
        return [], [' '.join(tokens)]
    out: List[str] = []
    removed: List[str] = []
    i, n = 0, len(tokens)
    while i < n:
        if tokens[i] in number_tokens and i + 1 < n and tokens[i + 1].isdigit():
            removed.append(' '.join(tokens[i:i + 2]))
            i += 2
            continue
        token = tokens[i]
        if 'po box' in patterns and ((token == 'po' and i + 1 < n and tokens[i + 1] == 'box') or
                                     (token == 'p' and i + 2 < n and tokens[i + 1] == 'o' and tokens[i + 2] == 'box')):
            j = i + (2 if token == 'po' else 3)
            if j < n and tokens[j].isdigit():
                j += 1
            removed.append(' '.join(tokens[i:j]))
            i = j
            continue
        if token in noise:
            j = i + 1
            if token in _TAKES_NUMBER and j < n and tokens[j].isdigit():
                j += 1
            removed.append(' '.join(tokens[i:j]))
            i = j
            continue
        out.append(token)
        i += 1
    return out, removed


def _drop_number_labels(tokens: List[str]) -> List[str]:
    """Drop the label ``no`` directly before a number. Repeated until stable so the view is idempotent: ``No No 4`` -> ``No 4`` -> ``4``."""
    while True:
        kept = [t for i, t in enumerate(tokens) if not (t in _LABEL_TOKENS and i + 1 < len(tokens) and tokens[i + 1][:1].isdigit())]
        if len(kept) == len(tokens):
            return tokens
        tokens = kept


def _expand(tokens: List[str], abbrev: Dict[str, Tuple[str, str]]) -> List[str]:
    if not abbrev:
        return tokens
    out = []
    last = len(tokens) - 1
    for i, token in enumerate(tokens):
        hit = abbrev.get(token)
        if hit is None:
            out.append(token)
            continue
        expansion, rule = hit
        if rule == 'any':
            take = True
        elif rule == 'suffix_multi' and i == 0:
            take = False          # a whole-segment ``CT`` is Connecticut, not Court
        else:
            take = i == last or tokens[i + 1] in _UNIT_WORDS or tokens[i + 1][:1].isdigit()
        if take:
            out.append(expansion)
        else:
            out.append(token)
    return out


def _drop_labels_across_segments(token_lists: List[List[str]]) -> List[List[str]]:
    """A label separated from its number by a comma (``Plot No, 93``) is dropped like ``Plot No 93``; the segment ends up without it. Repeated
    until stable, which also makes the joined view a fixed point of the same rule applied to a single segment."""
    while True:
        token_lists = [tokens for tokens in token_lists if tokens]
        changed = False
        for i in range(len(token_lists) - 1):
            if token_lists[i][-1] in _LABEL_TOKENS and token_lists[i + 1][0][:1].isdigit():
                token_lists[i] = token_lists[i][:-1]
                changed = True
        if not changed:
            return token_lists


def canon_segments(cleaned: str, country: str, drop_labels: bool = True, remove_extras: bool = True):
    """Canonical segments in original order plus the states found, the placeholder count and the removed injected components."""
    forms = state_forms(country)
    abbrev = address_abbrev(country)
    placeholders = address_placeholder_segments(country)
    token_lists: List[List[str]] = []
    nulls = 0
    extras: List[str] = []
    for segment in cleaned.split(','):
        tokens = [_strip_zeros(t) for t in _tokens(segment)]      # zeros first: ``B03`` must meet the noise and label rules as ``b3``
        if not tokens:
            continue
        if ' '.join(tokens) in placeholders:
            nulls += 1
            continue
        if remove_extras:
            tokens, removed = _remove_noise(tokens, country)
            extras += removed
        if drop_labels:
            tokens = _drop_number_labels(tokens)
        token_lists.append(tokens)
    if drop_labels:
        token_lists = _drop_labels_across_segments(token_lists)
    segments: List[str] = []
    states: List[Tuple[int, str, str]] = []     # (segment index, canonical, kind)
    for tokens in token_lists:
        tokens = _expand(tokens, abbrev)
        if not tokens:
            continue
        text = ' '.join(tokens)
        hit = forms.get(text)
        if hit is not None:
            states.append((len(segments), hit[0], hit[1]))
            text = hit[0]
        segments.append(text)
    return segments, states, nulls, extras


def number_spans(cleaned: str) -> List[Tuple[str, str, str]]:
    """(raw span, canonical span, context) for every number span, in order. Context = up to two tokens before the span in its segment."""
    spans = []
    for segment in cleaned.split(','):
        for match in _NUM_SPAN.finditer(segment):
            raw = match.group(0)
            context = ' '.join(_tokens(segment[:match.start()])[-2:])
            spans.append((raw, canon_number(raw), context))
    return spans


def _state_result(states: List[Tuple[int, str, str]]) -> Tuple[str, str, Optional[int]]:
    if not states:
        return '', 'none', None
    canonicals = {c for _i, c, _k in states}
    if len(canonicals) > 1:
        return '', 'conflict', None
    best = min(states, key=lambda s: (_KIND_RANK[s[2]], s[0]))
    return best[1], _KIND_CONF[best[2]], best[0]


def _city_candidates(segments: List[str], states: List[Tuple[int, str, str]], state_index: Optional[int]) -> List[str]:
    state_positions = {i for i, _c, _k in states}
    candidates = [(i, s) for i, s in enumerate(segments)
                  if i not in state_positions and not any(c.isdigit() for c in s) and not (set(s.split()) & _STREET_WORDS) and len(s.split()) <= 4]
    if state_index is not None:
        candidates.sort(key=lambda item: (abs(item[0] - state_index), item[0]))
    else:
        candidates.sort(key=lambda item: -item[0])
    seen, out = set(), []
    for _i, text in candidates:
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:3]


def _empty(raw_missing: bool) -> Dict[str, object]:
    return {'address_canon': '', 'address_tokset': '', 'address_segset': '', 'address_segments': [], 'address_nsegments': 0,
            'address_numbers_raw': [], 'address_numbers_canon': [], 'address_number_ctx': [], 'address_postal_candidates': [],
            'address_state_canon': '', 'address_state_conf': 'none', 'address_city_candidates': [], 'address_scripts': 0,
            'address_null_tokens': 0, 'address_had_leading_zero': False, 'address_extras': '',
            'address_parse_conf': 'missing' if raw_missing else 'low'}


def build_address_features(raw: str, country: str, cleaned: Optional[str] = None, drop_labels: bool = True,
                           remove_extras: bool = True) -> Dict[str, object]:
    """All Phase 5 address columns for one record. Lists are never None; empty means empty; a missing address is a flag."""
    if raw.strip() == '':
        return _empty(True)
    if cleaned is None:
        cleaned, _ = h.clean_text(raw)
    segments, states, nulls, extras = canon_segments(cleaned, country, drop_labels, remove_extras)
    spans = number_spans(cleaned)
    state, conf, state_index = _state_result(states)
    tokens = ' '.join(segments).split()
    if conf in ('exact', 'alias', 'mapped_native', 'mapped_department') and spans:
        parse_conf = 'high'
    elif conf in ('exact', 'alias', 'mapped_native', 'mapped_department') or spans:
        parse_conf = 'medium'
    else:
        parse_conf = 'low'
    return {
        'address_canon': ' '.join(tokens),
        'address_tokset': ' '.join(sorted(set(tokens))),
        'address_segset': '|'.join(sorted(set(segments))),
        'address_segments': segments,
        'address_nsegments': len(segments),
        'address_numbers_raw': [s[0] for s in spans],
        'address_numbers_canon': [s[1] for s in spans],
        'address_number_ctx': [s[2] for s in spans],
        'address_postal_candidates': sorted(set(_POSTAL.findall(cleaned))),
        'address_state_canon': state,
        'address_state_conf': conf,
        'address_city_candidates': _city_candidates(segments, states, state_index),
        'address_scripts': T.script_mask(raw),
        'address_null_tokens': nulls,
        'address_had_leading_zero': _LEADING_ZERO.search(cleaned) is not None,
        'address_extras': ' | '.join(extras),
        'address_parse_conf': parse_conf,
    }
