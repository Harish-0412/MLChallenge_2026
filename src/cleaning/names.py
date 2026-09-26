"""Phase 3: business-name features (feat_v2_0).

Everything here is derived from the hygiene text and never replaces it. The full name and ``name_hyg`` stay available;
``name_core`` is a *matching view*, not an identity key (removing legal forms raises the share of Source 1 names that
share a key from 31% to about 41%; see reports/eda/cleaning_decisions.md, X-01).

Rules, each tied to a measured pattern:

* legal forms are extracted with country-scoped lexicons and recorded (canonical code + position) instead of deleted;
* brackets are boundaries, exactly as in the v1 key: dropping bracket text on its own lowers agreement (N-07). Bracket
  text is also kept in ``name_bracket_text`` and a legal form inside brackets is reported with position ``bracket``;
* ``.com`` names are parsed locally (never opened): the label becomes the tokens and ``name_core_compact`` joins them;
* ``NA``-style names are flagged, never nulled: all 24 such training targets are true links (N-10);
* injected leading words (``The``, ``Dr``, ``Mr``, ``Sri``, ``Shri``) and the connector ``and`` are removed from the core only.
"""
import json
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from . import text_hygiene as h
from . import translit as T
from .lexicons import appended_noise, generic_tokens, legal_index, noise_tokens, placeholder_names

_BRACKET_GROUP = re.compile(r'\([^()\[\]]*\)|\[[^()\[\]]*\]')
_DOMAIN = re.compile(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.com', re.IGNORECASE)      # only .com occurs (99.995% of domain-like names)
_NOISE_PREFIX = re.compile(r'[*>.\-#@_~|=+!]+')
_MS_PREFIX = re.compile(r'\s*[Mm]\s*/\s*[Ss](?![A-Za-z])')     # Indian "M/s" (Messrs): 25,677 S2 / 29,307 S3 train names vs 10 in S1
_ALIAS = re.compile(r'(?<![A-Za-z0-9])(d\s*/\s*b\s*/\s*a|dba|a\s*/\s*k\s*/\s*a|aka|f\s*/\s*k\s*/\s*a|fka|t\s*/\s*a|trading\s+as)(?![A-Za-z0-9])',
                    re.IGNORECASE)
_ALIAS_CODE = {'dba': 'dba', 'aka': 'aka', 'fka': 'fka', 'ta': 'ta', 'tradingas': 'trading_as'}

NAME_COLUMNS: Tuple[str, ...] = (
    'legal_form', 'legal_form_pos', 'name_core', 'name_core_fold', 'name_core_trim', 'name_core_fallback', 'name_core_set', 'name_core_compact',
    'name_leading_removed',
    'name_token_counts', 'name_ntokens', 'name_ncore', 'name_ninformative', 'name_bracket_text',
    'name_is_domain_like', 'name_domain_label', 'name_placeholder_like', 'name_noise_prefix',
    'name_alias_marker', 'name_alias_left', 'name_alias_right',
    'name_scripts', 'name_translit', 'name_skeleton',
)


def tokenize(text: str) -> Tuple[List[str], List[bool], List[str]]:
    """Tokens of ``text`` (same tokenisation as ``lmn_key``), a parallel in-bracket flag, and the bracket contents."""
    tokens: List[str] = []
    flags: List[bool] = []
    brackets: List[str] = []
    position = 0
    for match in _BRACKET_GROUP.finditer(text):
        for token in h.lmn_key(text[position:match.start()]).split():
            tokens.append(token)
            flags.append(False)
        inner = h.lmn_key(match.group(0)[1:-1]).split()
        if inner:
            brackets.append(' '.join(inner))
        for token in inner:
            tokens.append(token)
            flags.append(True)
        position = match.end()
    for token in h.lmn_key(text[position:]).split():
        tokens.append(token)
        flags.append(False)
    return tokens, flags, brackets


def legal_lookup(token: str, index: Dict[str, Tuple[str, int]]) -> Optional[Tuple[str, int]]:
    """Legal-form lookup that also accepts the accent-folded token: accent noise reaches legal words too
    (``límited`` 26k S2 / 36k S3 India, ``ínc`` 17k US, ``sàrl`` 5.5k France, all absent from S1)."""
    hit = index.get(token)
    if hit is None and not token.isascii():
        hit = index.get(h.fold_latin(token))
    return hit


def extract_legal(tokens: List[str], in_bracket: List[bool], index: Dict[str, Tuple[str, int]]) -> Tuple[List[bool], str, str]:
    """Mark legal tokens; return (marks, canonical code string ordered by rank, position class)."""
    hits = [legal_lookup(token, index) for token in tokens]
    marks = [hit is not None for hit in hits]
    if not any(marks):
        return marks, '', 'none'
    n = len(tokens)
    suffix_start = n
    while suffix_start > 0 and marks[suffix_start - 1]:
        suffix_start -= 1
    prefix_end = 0
    while prefix_end < n and marks[prefix_end]:
        prefix_end += 1
    kinds = set()
    for i, marked in enumerate(marks):
        if not marked:
            continue
        if in_bracket[i]:
            kinds.add('bracket')
        elif i >= suffix_start:
            kinds.add('suffix')
        elif i < prefix_end:
            kinds.add('prefix')
        else:
            kinds.add('middle')
    codes = {hit[0]: hit[1] for hit in hits if hit is not None}
    code_string = '+'.join(sorted(codes, key=lambda c: (codes[c], c)))
    return marks, code_string, next(iter(kinds)) if len(kinds) == 1 else 'mixed'


def core_tokens(tokens: List[str], marks: List[bool], domain_like: bool, ms_prefix: bool = False) -> Tuple[List[str], List[str]]:
    """Core tokens and the leading words that were removed.

    Removes legal forms, ``M/s`` (raw-pattern, see ``ms_prefix``), injected leading words, the connector ``and`` and a
    domain's ``www``/``com``. The result is never empty unless every token was legal; the caller then falls back.
    """
    core = [t for t, m in zip(tokens, marks) if not m]
    removed: List[str] = []
    if ms_prefix and 'm/s' in noise_tokens('leading_pattern') and len(core) > 2 and core[:2] == ['m', 's']:
        removed.append('m/s')
        core = core[2:]
    if domain_like:
        if len(core) > 1 and core[-1] == 'com':
            core.pop()
        if len(core) > 1 and core[0] == 'www':
            core.pop(0)
    leading = noise_tokens('leading')
    while len(core) > 1 and core[0] in leading:
        removed.append(core.pop(0))
    connectors = noise_tokens('connector')
    kept = [t for t in core if t not in connectors]
    return (kept or core), removed


def trim_appended_noise(core: List[str], country: str) -> List[str]:
    """EXPERIMENTAL view: drop trailing filler words (Center, Services, Summit, ...) that S2/S3 append far more often than S1.

    Removing them conflates names such as ``Foo Summit`` and ``Foo Valley``, so this is a candidate/feature view whose
    collision cost is measured in Phase 8, never an identity key. Never removes the last remaining token.
    """
    noise = appended_noise(country)
    out = list(core)
    while len(out) > 1 and out[-1] in noise:
        out.pop()
    return out


def _alias_parts(cleaned: str, country: str, index) -> Tuple[str, str, str]:
    match = _ALIAS.search(cleaned)
    if not match:
        return '', '', ''
    marker = _ALIAS_CODE[re.sub(r'[^a-z]', '', match.group(1).lower())]
    parts = []
    for text in (cleaned[:match.start()], cleaned[match.end():]):
        tokens, flags, _ = tokenize(text)
        marks, _codes, _pos = extract_legal(tokens, flags, index)
        parts.append(' '.join(core_tokens(tokens, marks, False)[0]) if tokens else '')
    return marker, parts[0], parts[1]


def build_name_features(raw: str, country: str, cleaned: Optional[str] = None) -> Dict[str, object]:
    """All Phase 3 name columns for one record. Strings are never None; empty means empty."""
    if cleaned is None:
        cleaned, _ = h.clean_text(raw, join_legal_acronyms=True)
    index = legal_index(country)
    stripped = raw.strip()
    tokens, in_bracket, brackets = tokenize(cleaned)
    marks, legal_form, legal_pos = extract_legal(tokens, in_bracket, index)
    domain_like = _DOMAIN.fullmatch(stripped) is not None
    core, removed = core_tokens(tokens, marks, domain_like, _MS_PREFIX.match(cleaned) is not None)
    fallback = False
    if tokens and not [t for t, m in zip(tokens, marks) if not m]:
        core, fallback = list(tokens), True          # a name made only of legal words keeps its tokens
    generic = generic_tokens(country)
    duplicates = {t: n for t, n in Counter(core).items() if n > 1}
    prefix = _NOISE_PREFIX.match(stripped)
    marker, alias_left, alias_right = _alias_parts(cleaned, country, index)
    label = ''
    if domain_like:
        label = stripped.lower()[:-4]
        label = label[4:] if label.startswith('www.') and len(label) > 4 else label
    return {
        'legal_form': legal_form,
        'legal_form_pos': legal_pos,
        'name_core': ' '.join(core),
        'name_core_fold': ' '.join(h.fold_latin(t) for t in core),
        'name_core_trim': ' '.join(trim_appended_noise(core, country)),
        'name_core_fallback': fallback,
        'name_core_set': ' '.join(sorted(set(core))),
        'name_core_compact': ''.join(core),
        'name_leading_removed': ' '.join(removed),
        'name_token_counts': json.dumps(duplicates, sort_keys=True, ensure_ascii=False),
        'name_ntokens': len(tokens),
        'name_ncore': len(core),
        'name_ninformative': sum(1 for t in core if t not in generic),
        'name_bracket_text': ' | '.join(brackets),
        'name_is_domain_like': domain_like,
        'name_domain_label': label,
        'name_placeholder_like': stripped.lower() in placeholder_names(),
        'name_noise_prefix': prefix.group(0)[:4] if prefix else '',
        'name_alias_marker': marker,
        'name_alias_left': alias_left,
        'name_alias_right': alias_right,
        'name_scripts': T.script_mask(raw),
        'name_translit': T.name_translit(cleaned),
        'name_skeleton': T.name_skeleton(' '.join(core)),
    }
