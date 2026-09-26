"""Phase 6: the full feature record (feat_v2_0) and its explicit Arrow schema.

``build_row`` is the single entry point: identity and raw fields are copied unchanged; every other column comes from the
tested modules (text_hygiene, names, addresses, translit). Column order and types are fixed here and nowhere else.

Null semantics: strings are never NULL (empty string = empty view), lists are never NULL (empty list), booleans and integers are
never NULL. A missing address is the flag ``address_missing`` and ``address_parse_conf = 'missing'``; it is never filled.
"""
from functools import lru_cache
from typing import List, Tuple

import pyarrow as pa

from . import addresses as A
from . import names as N
from . import text_hygiene as h

INPUT_COLUMNS: Tuple[str, ...] = ('entity_id', 'business_name', 'business_address', 'country', 'name_key', 'address_key')
IDENTITY: Tuple[str, ...] = ('entity_id', 'id_num', 'source', 'split', 'country', 'business_name', 'business_address', 'name_key', 'address_key',
                             'feature_version', 'hygiene_version')
NAME_HYGIENE: Tuple[str, ...] = ('name_hyg', 'name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key', 'name_repairs',
                                 'name_has_control', 'name_has_format', 'name_mojibake', 'name_multispace')
ADDRESS_HYGIENE: Tuple[str, ...] = ('address_clean', 'address_missing', 'address_repairs', 'address_has_control', 'address_has_format',
                                    'address_mojibake', 'address_multispace')
DERIVED: Tuple[str, ...] = NAME_HYGIENE + N.NAME_COLUMNS + ADDRESS_HYGIENE + A.ADDRESS_COLUMNS
COLUMNS: Tuple[str, ...] = IDENTITY + DERIVED
assert len(set(COLUMNS)) == len(COLUMNS), 'duplicate column names'

_BOOL = frozenset({'name_has_control', 'name_has_format', 'name_mojibake', 'name_multispace', 'name_core_fallback', 'name_is_domain_like',
                   'name_placeholder_like', 'address_missing', 'address_has_control', 'address_has_format', 'address_mojibake',
                   'address_multispace', 'address_had_leading_zero'})
_INT = {'id_num': pa.int64(), 'source': pa.int8(), 'name_ntokens': pa.int16(), 'name_ncore': pa.int16(), 'name_ninformative': pa.int16(),
        'name_scripts': pa.int32(), 'address_scripts': pa.int32(), 'address_nsegments': pa.int16(), 'address_null_tokens': pa.int16()}
_LIST = frozenset({'address_segments', 'address_numbers_raw', 'address_numbers_canon', 'address_number_ctx', 'address_postal_candidates',
                   'address_city_candidates'})


def column_type(name: str) -> pa.DataType:
    if name in _BOOL:
        return pa.bool_()
    if name in _INT:
        return _INT[name]
    if name in _LIST:
        return pa.list_(pa.string())
    return pa.string()


SCHEMA = pa.schema([pa.field(name, column_type(name), nullable=False) for name in COLUMNS])


@lru_cache(maxsize=200_000)
def _name_part(name: str, country: str) -> tuple:
    hygiene, cleaned = h.name_hygiene(name)
    features = N.build_name_features(name, country, cleaned=cleaned)
    return tuple(hygiene[c] for c in NAME_HYGIENE) + tuple(features[c] for c in N.NAME_COLUMNS)


@lru_cache(maxsize=100_000)
def _address_part(address: str, country: str) -> tuple:
    hygiene, cleaned = h.address_hygiene(address)
    features = A.build_address_features(address, country, cleaned=cleaned)
    return tuple(hygiene[c] for c in ADDRESS_HYGIENE) + tuple(features[c] for c in A.ADDRESS_COLUMNS)


def build_row(entity_id: str, name: str, address: str, country: str, name_key: str, address_key: str,
              split: str, source: int, feature_version: str, hygiene_version: str) -> List[object]:
    """One feature record in COLUMNS order. Raw fields are passed through byte for byte."""
    return ([entity_id, int(entity_id.rsplit('-', 1)[1]), source, split, country, name, address, name_key, address_key,
             feature_version, hygiene_version] + list(_name_part(name, country)) + list(_address_part(address, country)))


def derived_values(name: str, address: str, country: str) -> dict:
    """Derived columns only, as a dict (used by verification to recompute a stored row)."""
    values = list(_name_part(name, country)) + list(_address_part(address, country))
    return dict(zip(DERIVED, values))


def clear_caches() -> None:
    _name_part.cache_clear()
    _address_part.cache_clear()
