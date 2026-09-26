"""Full-data scan of the Phase 2 hygiene layer. Everything here is read-only over the Parquet copies.

One task = one Parquet row group. Each task returns plain Counters and bounded example lists, which are merged in
the parent. Metrics (all keyed by (table, country, metric)):

* rows                       rows scanned
* repair:<field>:<code>      rows where that repair changed the string
* flag:<name>                rows where a flag is true
* v1_parity_fail:<field>     lmn_key(raw) != stored v1 key (the frozen rule, Python vs DuckDB)
* differs_v1:<view>          view differs from the v1 key (how much each view changes)
* empty:<view>               view is empty although the raw field is not blank (v1 has none)
* addr_new_empty             address had a non-empty v1 key but its cleaned view has an empty key
* mn_lost:<field>            a mark (M) or number (N) code point present in NFC(raw) is missing from the view
* not_idempotent:<view>      applying the view again changes it
"""
import unicodedata
import zlib
from collections import Counter
from typing import Dict, List, Tuple

from . import text_hygiene as h

COLUMNS = ['entity_id', 'business_name', 'business_address', 'country', 'name_key', 'address_key']
EXAMPLES_PER_CODE = 4
FTFY_SAMPLE_MODULUS = 240          # deterministic ~0.4% sample of rows for the ftfy false-positive check
NAME_VIEWS = ('name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key')


def _mn(text: str) -> Counter:
    return Counter(c for c in text if unicodedata.category(c)[0] in 'MN')


def mn_lost(raw: str, view: str) -> bool:
    """True if a mark or number code point of NFC(raw) occurs fewer times in view."""
    nfc_raw = unicodedata.normalize('NFC', raw)
    if nfc_raw.isascii():
        return sorted(c for c in nfc_raw if c.isdigit()) != sorted(c for c in view if c.isdigit())
    want, got = _mn(nfc_raw), _mn(view)
    return any(got[c] < n for c, n in want.items())


def scan_rows(table: str, rows, dotted) -> dict:
    """Scan an iterable of (entity_id, name, address, country, name_key, address_key)."""
    counts: Counter = Counter()
    dotted_census: Counter = Counter()
    examples: Dict[Tuple[str, str], List[tuple]] = {}
    flagged: List[tuple] = []
    sample: List[tuple] = []
    parity_failures: List[tuple] = []

    def bump(country, metric, n=1):
        counts[(table, country, metric)] += n

    def keep_example(field, code, eid, raw, cleaned):
        bucket = examples.setdefault((field, code), [])
        bucket.append((eid, raw, cleaned))
        if len(bucket) > EXAMPLES_PER_CODE * 3:
            bucket.sort()
            del bucket[EXAMPLES_PER_CODE:]

    for eid, name, address, country, name_key, address_key in rows:
        bump(country, 'rows')
        rec = h.hygiene_record(name, address, dotted)

        # parity of the frozen v1 rule between Python and the DuckDB-computed keys stored in the Parquet copies
        for field, raw, stored in (('name', name, name_key), ('address', address, address_key)):
            if h.lmn_key(raw) != stored:
                bump(country, f'v1_parity_fail:{field}')
                if len(parity_failures) < 20:
                    parity_failures.append((table, eid, field, raw, stored, h.lmn_key(raw)))

        for field, codes, cleaned, raw in (('name', rec['name_repairs'], rec['name_hyg'], name),
                                           ('address', rec['address_repairs'], rec['address_clean'], address)):
            for code in filter(None, codes.split(',')):
                bump(country, f'repair:{field}:{code}')
                keep_example(field, code, eid, raw, cleaned)

        for flag in ('has_control', 'has_format', 'mojibake', 'multispace'):
            for field in ('name', 'address'):
                if rec[f'{field}_{flag}']:
                    bump(country, f'flag:{field}_{flag}')
        if rec['address_missing']:
            bump(country, 'flag:address_missing')
        if rec['name_has_control'] or rec['address_has_control']:
            bump(country, 'flag:any_control')
        if rec['name_has_format'] or rec['address_has_format']:
            bump(country, 'flag:any_format')
        if rec['name_mojibake'] or rec['address_mojibake'] or rec['name_has_control'] or rec['address_has_control']:
            flagged.append((table, eid, name, address))

        # how much does each view differ from the v1 key, and does any view lose a non-blank name
        for view in ('name_hyg',) + NAME_VIEWS:
            if rec[view] != name_key:
                bump(country, f'differs_v1:{view}')
            if rec[view] == '' and name.strip():
                bump(country, f'empty:{view}')
        address_view_key = h.lmn_key(rec['address_clean'])
        if address_view_key != address_key:
            bump(country, 'differs_v1:address_clean')
        if address_key and not address_view_key:
            bump(country, 'addr_new_empty')

        # preservation and idempotence over every row
        if mn_lost(name, rec['name_hyg']):
            bump(country, 'mn_lost:name_hyg')
        if mn_lost(address, rec['address_clean']):
            bump(country, 'mn_lost:address_clean')
        again = h.hygiene_record(rec['name_hyg'], rec['address_clean'], dotted)
        if again['name_hyg'] != rec['name_hyg']:
            bump(country, 'not_idempotent:name_hyg')
        if again['address_clean'] != rec['address_clean']:
            bump(country, 'not_idempotent:address_clean')
        for view in NAME_VIEWS:
            if rec[view] != rec['name_hyg']:      # only meaningful when the view is not just name_hyg again
                if h.hygiene_record(rec[view], '', dotted)[view] != rec[view]:
                    bump(country, f'not_idempotent:{view}')

        if '.' in name:
            for match in h._DOTTED_ACRONYM.finditer(name):
                dotted_census[match.group(0).replace('.', '').lower()] += 1
        if zlib.crc32(eid.encode()) % FTFY_SAMPLE_MODULUS == 0:
            sample.append((table, eid, name, address))

    return {'counts': counts, 'dotted_census': dotted_census, 'examples': examples, 'flagged': flagged,
            'sample': sample, 'parity_failures': parity_failures}


def scan_row_group(task) -> dict:
    """Process-pool entry point: (table, parquet_path, row_group_index) -> result dict (plus timing and peak memory)."""
    import time
    import psutil
    import pyarrow.parquet as pq
    table, path, group = task
    started = time.perf_counter()
    data = pq.ParquetFile(path).read_row_group(group, columns=COLUMNS).to_pydict()
    result = scan_rows(table, zip(*(data[c] for c in COLUMNS)), h.legal_dotted())
    info = psutil.Process().memory_info()
    result['seconds'] = time.perf_counter() - started
    result['rows'] = len(data['entity_id'])
    result['peak_memory_mb'] = round(getattr(info, 'peak_wset', info.rss) / 2 ** 20)
    return result


def merge(results) -> dict:
    merged = {'counts': Counter(), 'dotted_census': Counter(), 'examples': {}, 'flagged': [], 'sample': [],
              'parity_failures': [], 'seconds': 0.0, 'rows': 0, 'peak_memory_mb': 0}
    for r in results:
        merged['counts'].update(r['counts'])
        merged['dotted_census'].update(r['dotted_census'])
        merged['flagged'] += r['flagged']
        merged['sample'] += r['sample']
        merged['parity_failures'] += r['parity_failures']
        merged['seconds'] += r.get('seconds', 0.0)
        merged['rows'] += r.get('rows', 0)
        merged['peak_memory_mb'] = max(merged['peak_memory_mb'], r.get('peak_memory_mb', 0))
        for key, items in r['examples'].items():
            merged['examples'].setdefault(key, []).extend(items)
    for key, items in merged['examples'].items():
        items.sort()
        merged['examples'][key] = items[:EXAMPLES_PER_CODE]
    merged['flagged'].sort()
    merged['sample'].sort()
    merged['parity_failures'].sort()
    return merged
