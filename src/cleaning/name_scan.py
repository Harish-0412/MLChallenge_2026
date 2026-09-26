"""Full-data scan of the Phase 3 name features. Read-only over the Parquet copies.

One task = one Parquet row group. Metrics (keyed by (table, country, metric)):

* rows, legal_code:<CODE>, legal_pos:<pos>, fallback, placeholder, domain_like, noise_prefix:<p>, alias:<marker>, leading:<word>,
  bracket_text, ms_pattern_rows, ninformative_0, ninformative_1, core_differs_v1, trim_changes
* violation:core_empty, violation:not_subsequence, violation:not_idempotent, violation:ntokens, violation:set_or_compact,
  violation:unknown_code, violation:pos_mismatch, violation:fallback_mismatch
Source 1 rows additionally write their keys to <scratch>/<table>_<group>.parquet for the collision analysis.
"""
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from . import names as N
from . import text_hygiene as h
from . import translit as T
from .lexicons import legal_dotted, _legal_rows

COLUMNS = ['entity_id', 'business_name', 'business_address', 'country', 'name_key']
KEY_COLUMNS = ['country', 'name_key', 'name_hyg', 'name_latin_accent_key', 'name_core', 'name_core_fold', 'name_core_trim',
               'name_core_set', 'name_core_compact', 'name_skeleton']
EXAMPLES_PER_KEY = 4


def scan_rows(table: str, rows, collect_keys: bool = False):
    """Scan an iterable of (entity_id, name, address, country, name_key)."""
    counts: Counter = Counter()
    examples: Dict[str, List[tuple]] = {}
    keys: Dict[str, list] = {c: [] for c in KEY_COLUMNS} if collect_keys else {}
    codes = {code for _t, _tok, code, _r in _legal_rows()}
    dotted = legal_dotted()

    def bump(country, metric, n=1):
        counts[(table, country, metric)] += n

    def example(kind, eid, raw, value):
        bucket = examples.setdefault(kind, [])
        bucket.append((eid, raw, value))
        if len(bucket) > EXAMPLES_PER_KEY * 3:
            bucket.sort()
            del bucket[EXAMPLES_PER_KEY:]

    for eid, raw, address, country, name_key in rows:
        bump(country, 'rows')
        cleaned, _repairs = h.clean_text(raw, dotted=dotted, join_legal_acronyms=True)
        name_hyg = h.lmn_key(cleaned)
        f = N.build_name_features(raw, country, cleaned=cleaned)
        hyg_tokens = name_hyg.split()
        core_tokens = f['name_core'].split()

        # ---- structural invariants (all rows)
        if raw.strip() and not core_tokens and hyg_tokens:
            bump(country, 'violation:core_empty')
        it = iter(hyg_tokens)
        if not all(tok in it for tok in core_tokens):
            bump(country, 'violation:not_subsequence')
            example('violation:not_subsequence', eid, raw, f['name_core'])
        if f['name_ntokens'] != len(hyg_tokens) or f['name_ncore'] != len(core_tokens):
            bump(country, 'violation:ntokens')
        if f['name_core_set'] != ' '.join(sorted(set(core_tokens))) or f['name_core_compact'] != ''.join(core_tokens):
            bump(country, 'violation:set_or_compact')
        if not set(filter(None, f['legal_form'].split('+'))) <= codes:
            bump(country, 'violation:unknown_code')
        if (f['legal_form'] == '') != (f['legal_form_pos'] == 'none'):
            bump(country, 'violation:pos_mismatch')
        if f['name_core_fallback'] and (core_tokens != hyg_tokens or not f['legal_form']):
            bump(country, 'violation:fallback_mismatch')
        again = N.build_name_features(f['name_core'], country)
        if again['name_core'] != f['name_core']:
            bump(country, 'violation:not_idempotent')
            example('violation:not_idempotent', eid, raw, f"{f['name_core']} -> {again['name_core']}")

        # ---- descriptive counts
        for code in filter(None, f['legal_form'].split('+')):
            bump(country, f'legal_code:{code}')
        if f['legal_form']:
            bump(country, f"legal_pos:{f['legal_form_pos']}")
            bump(country, 'has_legal_form')
            example(f"legal_pos:{f['legal_form_pos']}", eid, raw, f"{f['legal_form']} | {f['name_core']}")
        if f['name_core_fallback']:
            bump(country, 'fallback')
            example('fallback', eid, raw, f['name_core'])
        if f['name_placeholder_like']:
            bump(country, 'placeholder')
            example('placeholder', eid, raw, f['name_core'])
        if f['name_is_domain_like']:
            bump(country, 'domain_like')
            example('domain_like', eid, raw, f"{f['name_domain_label']} | {f['name_core']}")
        if f['name_noise_prefix']:
            bump(country, 'noise_prefix')
            bump(country, f"noise_prefix:{f['name_noise_prefix']}")
        if f['name_alias_marker']:
            bump(country, f"alias:{f['name_alias_marker']}")
            example(f"alias:{f['name_alias_marker']}", eid, raw, f"{f['name_alias_left']} || {f['name_alias_right']}")
        for word in f['name_leading_removed'].split():
            bump(country, f'leading:{word}')
        if f['name_leading_removed']:
            example('leading_removed', eid, raw, f"{f['name_leading_removed']} -> {f['name_core']}")
        if f['name_bracket_text']:
            bump(country, 'bracket_text')
        if N._MS_PREFIX.match(cleaned):
            bump(country, 'ms_pattern_rows')
        if f['name_ninformative'] == 0:
            bump(country, 'ninformative_0')
        elif f['name_ninformative'] == 1:
            bump(country, 'ninformative_1')
        if f['name_core'] != name_key:
            bump(country, 'core_differs_v1')
        if f['name_core_trim'] != f['name_core']:
            bump(country, 'trim_changes')
            example('trim_changes', eid, raw, f"{f['name_core']} -> {f['name_core_trim']}")

        # ---- scripts, transliteration and skeleton (all rows)
        name_mask, address_mask = f['name_scripts'], T.script_mask(address)
        for field, mask in (('name', name_mask), ('address', address_mask)):
            for script in T.script_names(mask):
                bump(country, f'script:{script}:{field}')
        if T.has_indic(name_mask):
            bump(country, 'indic_names')
            if name_mask & T.SCRIPT_BITS['Latin']:
                bump(country, 'mixed_script_names')
            if f['legal_form']:
                bump(country, 'indic_names_with_legal_form')
        translit = f['name_translit']
        if not translit.isascii():
            bump(country, 'violation:translit_not_ascii')
        if translit != h.lmn_key(translit):
            bump(country, 'violation:translit_not_normalised')
        if h.hygiene_record(raw, '')['name_hyg'] and not translit:
            bump(country, 'violation:translit_empty')
        skel = f['name_skeleton']
        if not skel.isascii() or T.skeleton(skel) != skel:
            bump(country, 'violation:skeleton_not_idempotent_or_ascii')
        # digits and punctuation are script-neutral (a name such as '1 800' has mask 0), so compare with LETTERS only
        if bool(name_mask) != any(c.isalpha() for c in raw):
            bump(country, 'violation:scripts_mask_vs_letters')
        if name_mask & T.SCRIPT_BITS['Other'] or address_mask & T.SCRIPT_BITS['Other']:
            bump(country, 'other_script_rows')
            example('other_script', eid, raw, address[:60])

        if collect_keys:
            values = {'country': country, 'name_key': name_key, 'name_hyg': name_hyg,
                      'name_latin_accent_key': h.lmn_key(h.fold_latin(h.nfc(raw))), 'name_core': f['name_core'],
                      'name_core_fold': f['name_core_fold'], 'name_core_trim': f['name_core_trim'],
                      'name_core_set': f['name_core_set'], 'name_core_compact': f['name_core_compact'], 'name_skeleton': f['name_skeleton']}
            for column in KEY_COLUMNS:
                keys[column].append(values[column])
    return counts, examples, keys


def scan_row_group(task) -> dict:
    """Process-pool entry point: (table, parquet_path, group, scratch_dir or None)."""
    import time
    import psutil
    import pyarrow as pa
    import pyarrow.parquet as pq
    table, path, group, scratch = task
    started = time.perf_counter()
    data = pq.ParquetFile(path).read_row_group(group, columns=COLUMNS).to_pydict()
    counts, examples, keys = scan_rows(table, zip(*(data[c] for c in COLUMNS)), collect_keys=bool(scratch))
    if scratch:
        Path(scratch).mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table(keys), Path(scratch) / f'{table}_{group:04d}.parquet', compression='zstd')
    info = psutil.Process().memory_info()
    return {'counts': counts, 'examples': examples, 'rows': len(data['entity_id']), 'seconds': time.perf_counter() - started,
            'peak_memory_mb': round(getattr(info, 'peak_wset', info.rss) / 2 ** 20)}


def merge(results) -> dict:
    merged = {'counts': Counter(), 'examples': {}, 'rows': 0, 'seconds': 0.0, 'peak_memory_mb': 0}
    for r in results:
        merged['counts'].update(r['counts'])
        merged['rows'] += r['rows']
        merged['seconds'] += r['seconds']
        merged['peak_memory_mb'] = max(merged['peak_memory_mb'], r['peak_memory_mb'])
        for kind, items in r['examples'].items():
            merged['examples'].setdefault(kind, []).extend(items)
    for kind, items in merged['examples'].items():
        items.sort()
        merged['examples'][kind] = items[:EXAMPLES_PER_KEY]
    return merged
