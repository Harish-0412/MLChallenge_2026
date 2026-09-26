"""Phase 6 verification of a built feature table (used by scripts/verify_features.py and by the unit tests).

Every check is a statement that can fail. The checks are deliberately restated in DuckDB SQL / pyarrow instead of calling the code under
test, and each block is exercised by a sabotage test (tests/test_feature_verify.py) that proves it can fail.

    A  files      schema, row counts, byte sizes and file set equal the build manifest; the table was built from the CURRENT code and lexicons
    B  coverage   every input row is present once, raw fields are byte-identical (join to the input Parquet copies; sums/hash/counts vs
                  manifests/input_manifest_v1.json on a full build)
    C  integrity  no NULLs anywhere (incl. list elements); hive partition path == in-file values
    D  invariants independent SQL restatements of the identity, hygiene, name and address rules (each must count 0 violating rows)
    E  scans      table-level counts reproduce the earlier full-data scan reports (name_scan_counts.csv, hygiene_change_counts.csv)
    F  recompute  stored rows == rows recomputed by the Python code (hash sample + stratified strata + extremes); v1 keys via the frozen rule
    G  determinism a scratch rebuild (different workers/flush) reproduces the table, byte-for-byte when the row-group layout is identical
"""
import csv
import json
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, unquote

from . import FEATURE_VERSION, HYGIENE_VERSION
from . import addresses as A
from . import names as N
from . import pipeline, record
from . import translit as T
from .lexicons import _legal_rows, all_lexicon_hashes
from .manifest import SOURCE_TABLES, sha256_file

V1_SQL = r"trim(regexp_replace(lower(nfc_normalize({col})), '[^\p{{L}}\p{{M}}\p{{N}}]+', ' ', 'g'))"
STATE_OK = "('exact','alias','mapped_native','mapped_department')"
INDIC_RE = ('Devanagari', 'Bengali', 'Gurmukhi', 'Gujarati', 'Oriya', 'Tamil', 'Telugu', 'Kannada', 'Malayalam')


def v1(col: str) -> str:
    return V1_SQL.format(col=col)


def rx(col: str, pattern: str) -> str:
    assert "'" not in pattern
    return f"regexp_matches({col}, '{pattern}')"


class Report:
    def __init__(self, echo: bool = True):
        self.checks: List[dict] = []
        self.echo = echo

    def add(self, name: str, ok: bool, detail: str = '') -> bool:
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        if self.echo:
            print(('PASS  ' if ok else 'FAIL  ') + name + (f'   [{detail}]' if detail else ''), flush=True)
        return bool(ok)

    @property
    def failed(self) -> List[dict]:
        return [c for c in self.checks if not c['ok']]

    def to_json(self) -> dict:
        return {'passed': len(self.checks) - len(self.failed), 'failed': len(self.failed), 'checks': self.checks}


def connect(threads: int = 8, memory: str = '9GB'):
    import duckdb
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='{memory}'; SET preserve_insertion_order=false")
    return con


def glob_of(fdir: Path, split: str = '*', source: str = '*') -> str:
    return (fdir / f'split={split}' / f'source={source}' / '*' / '*.parquet').as_posix()


def register(con, fdir: Path) -> None:
    con.execute(f"CREATE OR REPLACE VIEW f AS SELECT * FROM read_parquet('{glob_of(fdir)}', hive_partitioning=false, filename=true)")


# ------------------------------------------------------------------------------------------------------------------------------ A
def check_files(rep: Report, root: Path, fdir: Path) -> dict:
    import pyarrow.parquet as pq
    manifest = json.loads((fdir / '_manifest.json').read_text(encoding='utf-8'))
    rep.add('A1 manifest schema == record.SCHEMA (names, types, order)',
            [(c['name'], c['type']) for c in manifest['schema']] == [(f.name, str(f.type)) for f in record.SCHEMA],
            f'{len(manifest["schema"])} columns')
    listed = {f['path']: f for part in manifest['partitions'] for f in part['files']}
    on_disk = {p.relative_to(fdir).as_posix(): p for p in fdir.rglob('*.parquet')}
    rep.add('A2 parquet files on disk == files listed in the manifest', set(listed) == set(on_disk), f'{len(on_disk)} files')
    bad_schema, bad_rows, bad_bytes, rows = [], [], [], 0
    for rel, path in on_disk.items():
        pf = pq.ParquetFile(path)
        rows += pf.metadata.num_rows
        if not pf.schema_arrow.equals(record.SCHEMA, check_metadata=False):
            bad_schema.append(rel)
        info = listed.get(rel)
        if info and pf.metadata.num_rows != info['rows']:
            bad_rows.append(rel)
        if info and path.stat().st_size != info['bytes']:
            bad_bytes.append(rel)
    rep.add('A3 every file has exactly the record schema (incl. non-nullable)', not bad_schema, f'{len(bad_schema)} bad')
    rep.add('A4 per-file row counts and byte sizes == manifest', not bad_rows and not bad_bytes, f'rows {len(bad_rows)} bad, bytes {len(bad_bytes)} bad')
    rep.add('A5 total rows == manifest totals', rows == manifest['totals']['rows'], f'{rows:,}')
    stray = sorted(p.name for p in fdir.iterdir() if p.is_file() and p.name not in ('_manifest.json', '_run.json'))
    rep.add('A6 no stray files, no leftover .tmp directory', not stray and not fdir.with_name(fdir.name + '.tmp').exists(), f'stray={stray}')
    current = {'source_tree_sha256': pipeline.source_tree_hash(root), 'lexicon_sha256': all_lexicon_hashes()}
    rep.add('A7 built from the CURRENT source tree and lexicons (hashes recorded in the manifest)',
            all(manifest[k] == v for k, v in current.items()), f'tree {manifest["source_tree_sha256"][:12]}')
    input_manifest = root / 'manifests' / 'input_manifest_v1.json'
    if input_manifest.exists():
        rep.add('A8 built against the current input manifest', manifest['input_manifest_sha256'] == sha256_file(input_manifest))
    rep.add('A9 versions recorded', manifest['hygiene_version'] == HYGIENE_VERSION and manifest['feature_version'] == fdir.name,
            f'{manifest["feature_version"]} / {manifest["hygiene_version"]}')
    return manifest


# ------------------------------------------------------------------------------------------------------------------------------ B
def check_coverage(rep: Report, con, root: Path, fdir: Path, manifest: dict) -> None:
    import pyarrow.parquet as pq
    full = not manifest['sample_build']
    input_manifest = json.loads((root / 'manifests' / 'input_manifest_v1.json').read_text(encoding='utf-8')) if full else None
    for table in SOURCE_TABLES:
        split, source = table.split('_source')[0], table[-1]
        path = (root / 'data' / 'interim' / f'{table}.parquet').as_posix()
        g = glob_of(fdir, split, source)
        stats = con.execute(f"""SELECT count(*), count(DISTINCT entity_id), sum(length(business_name)), sum(length(business_address)),
                                sum(hash(entity_id, business_name, business_address, country))::HUGEINT FROM read_parquet('{g}')""").fetchone()
        per_country = dict(con.execute(f"SELECT country, count(*) FROM read_parquet('{g}') GROUP BY country").fetchall())
        blanks = dict(con.execute(f"SELECT country, sum(address_missing::INT) FROM read_parquet('{g}') GROUP BY country").fetchall())
        rep.add(f'B1 {table}: entity_id unique', stats[0] == stats[1], f'{stats[0]:,} rows')
        if full:
            m = input_manifest['files'][table]['parquet_copy']
            rep.add(f'B2 {table}: rows, name/address code points, content hash sum == input manifest',
                    (stats[0], stats[2], stats[3], str(stats[4])) == (m['rows'], m['name_codepoints'], m['address_codepoints'], m['content_hash_sum']),
                    f"rows {stats[0]:,} == {m['rows']:,}")
            rep.add(f'B3 {table}: per-country rows and blank addresses == input manifest',
                    per_country == {c: v['rows'] for c, v in m['per_country'].items()}
                    and all(int(blanks[c]) == v['blank_address'] for c, v in m['per_country'].items()),
                    ', '.join(f'{c} {n:,}' for c, n in sorted(per_country.items())))
        else:
            groups = min(manifest['max_row_groups_per_table'], pq.ParquetFile(path).num_row_groups)
            want = sum(pq.ParquetFile(path).metadata.row_group(i).num_rows for i in range(groups))
            rep.add(f'B2 {table}: rows == rows of the first {groups} input row group(s)', stats[0] == want, f'{stats[0]:,}')
        both = con.execute(f"""SELECT count(*), sum(CAST(f.business_name IS DISTINCT FROM r.business_name OR f.business_address IS DISTINCT FROM r.business_address
                                    OR f.country IS DISTINCT FROM r.country OR f.name_key IS DISTINCT FROM r.name_key OR f.address_key IS DISTINCT FROM r.address_key AS INT))
                               FROM read_parquet('{g}') f JOIN read_parquet('{path}') r USING (entity_id)""").fetchone()
        ok = both[0] == stats[0] and (both[1] or 0) == 0
        if full:
            total_input = con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
            ok = ok and total_input == stats[0]
        rep.add(f'B4 {table}: every row found in the input copy, raw fields and v1 keys identical' + (' (and no input row missing)' if full else ''),
                ok, f'joined {both[0]:,}, differing {both[1] or 0}')


# ------------------------------------------------------------------------------------------------------------------------------ C
def check_integrity(rep: Report, con, fdir: Path) -> None:
    scalar = [c for c in record.COLUMNS if c not in record._LIST]
    exprs = [f'count(*) - count("{c}")' for c in scalar] + [f'sum(len(list_filter("{c}", x -> x IS NULL)))' for c in sorted(record._LIST)]
    row = con.execute(f"SELECT {', '.join(exprs)} FROM f").fetchone()
    names = scalar + sorted(record._LIST)
    nulls = {n: v for n, v in zip(names, row) if v}
    total_rows = con.execute('SELECT count(*) FROM f').fetchone()[0]
    rep.add('C1 no NULL in any of the columns (list elements included)', not nulls, f'{len(names)} columns x {total_rows:,} rows; {nulls or "none"}')
    rows = con.execute(r"""SELECT DISTINCT split, CAST(source AS VARCHAR), country, regexp_extract(filename, 'split=([^/\\]+)', 1),
                           regexp_extract(filename, 'source=([^/\\]+)', 1), regexp_extract(filename, 'country=([^/\\]+)', 1) FROM f""").fetchall()
    bad = [r for r in rows if not (r[0] == r[3] and r[1] == r[4] and r[5] == quote(r[2], safe='') and unquote(r[5]) == r[2])]
    rep.add('C2 hive partition path (split/source/country, URL-quoted) == in-file column values for every file', not bad,
            f'{len(rows)} distinct partitions, {len(bad)} bad')
    rep.add('C3 country labels are exactly the three known values (a new label would be a data change to review)',
            {r[2] for r in rows} == {'India', 'US', 'France'}, str(sorted({r[2] for r in rows})))


# ------------------------------------------------------------------------------------------------------------------------------ D
def invariant_conditions(version: str) -> Dict[str, str]:
    """name -> SQL condition that is TRUE for a violating row. Each must count zero."""
    codes = sorted({code for _t, _tok, code, _r in _legal_rows()})
    code_list = '[' + ', '.join("'" + c.replace("'", "''") + "'" for c in codes) + ']'
    c: Dict[str, str] = {
        'D1 id_num == numeric suffix of entity_id': "id_num IS DISTINCT FROM TRY_CAST(regexp_extract(entity_id, '([0-9]+)$', 1) AS BIGINT)",
        'D2 entity_id starts with S<source>-': "NOT starts_with(entity_id, 'S' || CAST(source AS VARCHAR) || '-')",
        'D3 split is train|test': "split NOT IN ('train', 'test')",
        'D4 feature_version / hygiene_version constant': f"feature_version <> '{version}' OR hygiene_version <> '{HYGIENE_VERSION}'",
        'D5 name_key == frozen v1 rule (SQL) on the raw name': f"name_key IS DISTINCT FROM {v1('business_name')}",
        'D6 address_key == frozen v1 rule (SQL) on the raw address': f"address_key IS DISTINCT FROM {v1('business_address')}",
    }
    for field, col in (('name', 'business_name'), ('address', 'business_address')):
        for flag, pattern in (('has_control', r'\p{Cc}'), ('has_format', r'\p{Cf}'), ('mojibake', r'[\x{80}-\x{9F}\x{1A}]'),
                              ('multispace', r'[ \t\n\r\f\v]{2,}')):
            c[f'D7 {field}_{flag} == independent regex on the raw text'] = f"{field}_{flag} IS DISTINCT FROM {rx(col, pattern)}"
    c['D8 address_missing == blank after Unicode-whitespace strip'] = r"address_missing IS DISTINCT FROM regexp_matches(business_address, '^[\t-\r \x{1C}-\x{1F}\x{85}\p{Z}]*$')"
    for view in ('name_hyg', 'name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key'):
        c[f'D9 {view} is a fixed point of the v1 rule'] = f"{view} IS DISTINCT FROM {v1(view)}"
    c.update({
        'D10 name_ntokens == token count of name_hyg': "name_ntokens IS DISTINCT FROM CASE WHEN name_hyg = '' THEN 0 ELSE len(string_split(name_hyg, ' ')) END",
        'D11 name_ncore == token count of name_core': "name_ncore IS DISTINCT FROM CASE WHEN name_core = '' THEN 0 ELSE len(string_split(name_core, ' ')) END",
        'D12 name_core_set == sorted distinct core tokens': "name_core_set IS DISTINCT FROM array_to_string(list_sort(list_distinct(string_split(name_core, ' '))), ' ')",
        'D13 name_core_compact == core without spaces': "name_core_compact IS DISTINCT FROM replace(name_core, ' ', '')",
        'D14 legal_form empty <=> legal_form_pos none': "(legal_form = '') IS DISTINCT FROM (legal_form_pos = 'none')",
        'D15 legal_form_pos in the known set': "legal_form_pos NOT IN ('none', 'prefix', 'suffix', 'middle', 'bracket', 'mixed')",
        'D16 every legal_form code is a lexicon code': f"len(list_filter(string_split(legal_form, '+'), x -> x <> '' AND NOT list_contains({code_list}, x))) > 0",
        'D17 fallback core == whole name and has a legal form': "name_core_fallback AND (name_core <> name_hyg OR legal_form = '')",
        'D18 core never empty for a non-empty name': "name_hyg <> '' AND name_core = ''",
        'D19 core tokens are tokens of the cleaned name': "name_core <> '' AND len(list_filter(string_split(name_core, ' '), t -> NOT list_contains(string_split(name_hyg, ' '), t))) > 0",
        'D20 name_translit is ASCII': r"regexp_matches(name_translit, '[^\x{00}-\x{7F}]')",
        'D21 name_translit is a v1 fixed point': f"name_translit IS DISTINCT FROM {v1('name_translit')}",
        'D22 name_skeleton is ASCII': r"regexp_matches(name_skeleton, '[^\x{00}-\x{7F}]')",
        'D23 non-empty cleaned name has non-empty translit': "name_hyg <> '' AND name_translit = ''",
        'D24 name_ninformative <= name_ncore <= name_ntokens': "name_ninformative > name_ncore OR name_ncore > name_ntokens",
    })
    for field, col in (('name', 'business_name'), ('address', 'business_address')):
        for script in ('Latin',) + INDIC_RE:
            c[f'D25 {field}_scripts {script} bit == \\p{{{script}}} in the raw text'] = (
                f"((({field}_scripts >> {list(T.SCRIPT_BITS).index(script)}) & 1) = 1) IS DISTINCT FROM {rx(col, chr(92) + 'p{' + script + '}')}")
        c[f'D26 {field}_scripts Other bit implies a non-ASCII character'] = (
            f"((({field}_scripts >> {list(T.SCRIPT_BITS).index('Other')}) & 1) = 1) AND NOT " + rx(col, r'[^\x{00}-\x{7F}]'))
        c[f'D27 {field}_scripts below 2^11'] = f"{field}_scripts < 0 OR {field}_scripts >= 2048"
    c.update({
        'D30 address_nsegments == len(address_segments)': 'address_nsegments IS DISTINCT FROM len(address_segments)',
        'D31 address_canon == segments joined by single spaces': r"address_canon IS DISTINCT FROM trim(regexp_replace(coalesce(array_to_string(address_segments, ' '), ''), '\s+', ' ', 'g'))",
        'D32 address_tokset == sorted distinct canon tokens': "address_tokset IS DISTINCT FROM array_to_string(list_sort(list_distinct(string_split(address_canon, ' '))), ' ')",
        'D33 address_segset == sorted distinct segments joined by |': "address_segset IS DISTINCT FROM coalesce(array_to_string(list_sort(list_distinct(address_segments)), '|'), '')",
        'D34 numbers raw/canon/ctx lists have equal length': "len(address_numbers_raw) <> len(address_numbers_canon) OR len(address_numbers_raw) <> len(address_number_ctx)",
        'D35 address_parse_conf == missing | high | medium | low by the documented rule': f"""address_parse_conf IS DISTINCT FROM CASE
            WHEN address_missing THEN 'missing'
            WHEN address_state_conf IN {STATE_OK} AND len(address_numbers_raw) > 0 THEN 'high'
            WHEN address_state_conf IN {STATE_OK} OR len(address_numbers_raw) > 0 THEN 'medium' ELSE 'low' END""",
        'D36 a missing address has no derived content': """address_missing AND (address_nsegments > 0 OR address_canon <> '' OR address_state_canon <> '' OR address_state_conf <> 'none'
            OR len(address_postal_candidates) > 0 OR len(address_city_candidates) > 0 OR address_extras <> '' OR address_scripts <> 0 OR address_clean <> '')""",
        'D37 address_state_conf in the known set': "address_state_conf NOT IN ('exact', 'alias', 'mapped_native', 'mapped_department', 'conflict', 'none')",
        'D38 address_state_canon empty <=> conf is conflict|none': "(address_state_canon = '') IS DISTINCT FROM (address_state_conf IN ('conflict', 'none'))",
        'D39 postal candidates: 5 or 6 digits, sorted, distinct': r"""len(list_filter(address_postal_candidates, p -> NOT regexp_full_match(p, '\p{Nd}{5,6}'))) > 0
            OR address_postal_candidates IS DISTINCT FROM list_sort(list_distinct(address_postal_candidates))""",
        'D40 at most 3 city candidates, each is a segment, distinct': """len(address_city_candidates) > 3 OR len(list_filter(address_city_candidates, x -> NOT list_contains(address_segments, x))) > 0
            OR len(list_distinct(address_city_candidates)) <> len(address_city_candidates)""",
        'D41 removed injected components follow the per-country grammar (US: cdp, pmb n, po box n; India: hn n, b3, <x> region; France: none)':
            r"""address_extras <> '' AND (country NOT IN ('US', 'India')
            OR (country = 'US' AND len(list_filter(string_split(address_extras, ' | '), x -> NOT regexp_full_match(x, 'cdp|pmb( [0-9]+)?|(po|p o) box( [0-9]+)?'))) > 0)
            OR (country = 'India' AND len(list_filter(string_split(address_extras, ' | '), x -> NOT regexp_full_match(x, 'hn [0-9]+|b3|(.* )?region( .*)?'))) > 0))""",
        'D42 address_had_leading_zero == a 0-led digit run in address_clean': r"address_had_leading_zero IS DISTINCT FROM regexp_matches(address_clean, '(^|[^\p{Nd}])0\p{Nd}')",
        'D43 canonicalisation never drops or invents a digit run (rows without removed extras or stripped zeros)': r"""NOT address_missing AND address_extras = '' AND NOT address_had_leading_zero
            AND list_sort(regexp_extract_all(address_clean, '[0-9]+')) IS DISTINCT FROM list_sort(regexp_extract_all(address_canon, '[0-9]+'))""",
        'D44 address_null_tokens >= 0 and address_nsegments >= 0': "address_null_tokens < 0 OR address_nsegments < 0",
    })
    return c


def check_invariants(rep: Report, con, version: str, chunk: int = 12) -> None:
    conditions = invariant_conditions(version)
    names = list(conditions)
    for start in range(0, len(names), chunk):
        part = names[start:start + chunk]
        started = time.perf_counter()
        row = con.execute('SELECT ' + ', '.join(f'sum(CAST(({conditions[n]}) AS INT))' for n in part) + ' FROM f').fetchone()
        for name, value in zip(part, row):
            rep.add(name, (value or 0) == 0, f'{value or 0} violating rows')
        if rep.echo:
            print(f'      ({time.perf_counter() - started:.0f}s for {len(part)} conditions)', flush=True)


# ------------------------------------------------------------------------------------------------------------------------------ E
def metric_expressions(con) -> Dict[str, str]:
    """Metric name (as used by the earlier scans) -> SQL boolean/int expression per row."""
    q = lambda s: s.replace("'", "''")
    m: Dict[str, str] = {'rows': '1'}
    for flag in ('name_has_control', 'name_has_format', 'name_mojibake', 'name_multispace', 'address_has_control', 'address_has_format',
                 'address_mojibake', 'address_multispace', 'address_missing'):
        m[f'flag:{flag}'] = flag
    m['flag:any_control'] = '(name_has_control OR address_has_control)'
    m['flag:any_format'] = '(name_has_format OR address_has_format)'
    for view in ('name_hyg', 'name_latin_accent_key', 'name_joiner_key', 'name_compat_key', 'name_apos_join_key'):
        m[f'differs_v1:{view}'] = f'({view} <> name_key)'
    m['differs_v1:address_clean'] = f"({v1('address_clean')} <> address_key)"
    for field in ('name', 'address'):
        for code in [r[0] for r in con.execute(f"SELECT DISTINCT unnest(string_split({field}_repairs, ',')) FROM f WHERE {field}_repairs <> ''").fetchall()]:
            m[f'repair:{field}:{code}'] = f"list_contains(string_split({field}_repairs, ','), '{q(code)}')"
    for code in [r[0] for r in con.execute("SELECT DISTINCT unnest(string_split(legal_form, '+')) FROM f WHERE legal_form <> ''").fetchall()]:
        m[f'legal_code:{code}'] = f"list_contains(string_split(legal_form, '+'), '{q(code)}')"
    for pos in ('prefix', 'suffix', 'middle', 'bracket', 'mixed'):
        m[f'legal_pos:{pos}'] = f"(legal_form <> '' AND legal_form_pos = '{pos}')"
    m['has_legal_form'] = "(legal_form <> '')"
    m['fallback'] = 'name_core_fallback'
    m['placeholder'] = 'name_placeholder_like'
    m['domain_like'] = 'name_is_domain_like'
    m['noise_prefix'] = "(name_noise_prefix <> '')"
    for prefix in [r[0] for r in con.execute("SELECT DISTINCT name_noise_prefix FROM f WHERE name_noise_prefix <> ''").fetchall()]:
        m[f'noise_prefix:{prefix}'] = f"(name_noise_prefix = '{q(prefix)}')"
    for marker in [r[0] for r in con.execute("SELECT DISTINCT name_alias_marker FROM f WHERE name_alias_marker <> ''").fetchall()]:
        m[f'alias:{marker}'] = f"(name_alias_marker = '{q(marker)}')"
    for word in [r[0] for r in con.execute("SELECT DISTINCT unnest(string_split(name_leading_removed, ' ')) FROM f WHERE name_leading_removed <> ''").fetchall()]:
        m[f'leading:{word}'] = f"len(list_filter(string_split(name_leading_removed, ' '), x -> x = '{q(word)}'))"
    m['bracket_text'] = "(name_bracket_text <> '')"
    m['ninformative_0'] = '(name_ninformative = 0)'
    m['ninformative_1'] = '(name_ninformative = 1)'
    m['core_differs_v1'] = '(name_core <> name_key)'
    m['trim_changes'] = '(name_core_trim <> name_core)'
    indic = sum(T.SCRIPT_BITS[s] for s in T.INDIC_SCRIPTS)
    m['indic_names'] = f'((name_scripts & {indic}) > 0)'
    m['mixed_script_names'] = f"((name_scripts & {indic}) > 0 AND (name_scripts & {T.SCRIPT_BITS['Latin']}) > 0)"
    m['indic_names_with_legal_form'] = f"((name_scripts & {indic}) > 0 AND legal_form <> '')"
    for script, bit in T.SCRIPT_BITS.items():
        if script != 'Other':
            m[f'script:{script}:name'] = f'((name_scripts & {bit}) > 0)'
            m[f'script:{script}:address'] = f'((address_scripts & {bit}) > 0)'
    other = T.SCRIPT_BITS['Other']
    m['script:Other:name'] = f'((name_scripts & {other}) > 0)'
    m['script:Other:address'] = f'((address_scripts & {other}) > 0)'
    m['other_script_rows'] = f'((name_scripts & {other}) > 0 OR (address_scripts & {other}) > 0)'
    return m


NOT_RECOMPUTED_IN_SQL = ('ms_pattern_rows',)          # regex on the cleaned name with lookarounds; covered by the Python recompute sample


def check_scans(rep: Report, con, root: Path) -> None:
    metrics = metric_expressions(con)
    names = list(metrics)
    got: Dict[tuple, int] = {}
    for start in range(0, len(names), 40):
        part = names[start:start + 40]
        rows = con.execute('SELECT split, source, country, ' + ', '.join(f'sum(CAST(({metrics[n]}) AS BIGINT))' for n in part) + ' FROM f GROUP BY ALL').fetchall()
        for row in rows:
            table = f'{row[0]}_source{row[1]}'
            for n, v in zip(part, row[3:]):
                if v:
                    got[(table, row[2], n)] = int(v)
    for report_name in ('name_scan_counts.csv', 'hygiene_change_counts.csv'):
        expected: Dict[tuple, int] = {}
        with (root / 'reports' / 'cleaning' / report_name).open(encoding='utf-8', newline='') as fh:
            for r in csv.DictReader(fh):
                expected[(r['table'], r['country'], r['metric'])] = int(r['count'])
        skipped_metrics = {k[2] for k in expected if k[2] in NOT_RECOMPUTED_IN_SQL or k[2].startswith(('violation:', 'mn_lost', 'not_idempotent', 'empty:', 'v1_parity', 'addr_new'))}
        report_metrics = {k[2] for k in expected} - skipped_metrics
        compared = {k: v for k, v in got.items() if k[2] in report_metrics}
        # a metric family only counts as covered if the scan's CSV has it; SQL-only metrics of the other report are ignored here
        cells = set(compared) | {k for k in expected if k[2] not in skipped_metrics}
        wrong = [(k, expected.get(k, 0), compared.get(k, 0)) for k in sorted(cells) if expected.get(k, 0) != compared.get(k, 0)]
        rep.add(f'E {report_name}: table-level counts reproduce the earlier full-data scan',
                not wrong, f'{len(cells):,} (table, country, metric) cells compared, {len(wrong)} differ; skipped metrics: {sorted(skipped_metrics)[:6]}'
                + (f'; first differences {wrong[:5]}' if wrong else ''))


# ------------------------------------------------------------------------------------------------------------------------------ F
STRATA = {
    'name_mojibake': 'name_mojibake', 'name_has_control': 'name_has_control', 'name_has_format': 'name_has_format',
    'address_has_control': 'address_has_control', 'address_multispace': 'address_multispace', 'address_missing': 'address_missing',
    'legal_prefix': "legal_form_pos = 'prefix'", 'legal_suffix': "legal_form_pos = 'suffix'", 'legal_middle': "legal_form_pos IN ('middle','mixed','bracket')",
    'domain_like': 'name_is_domain_like', 'placeholder': 'name_placeholder_like', 'alias': "name_alias_marker <> ''", 'noise_prefix': "name_noise_prefix <> ''",
    'leading_removed': "name_leading_removed <> ''", 'bracket_text': "name_bracket_text <> ''", 'core_fallback': 'name_core_fallback',
    'state_conflict': "address_state_conf = 'conflict'", 'state_mapped_native': "address_state_conf = 'mapped_native'", 'state_department': "address_state_conf = 'mapped_department'",
    'extras': "address_extras <> ''", 'leading_zero': 'address_had_leading_zero', 'null_tokens': 'address_null_tokens > 0',
    'indic_name': f"(name_scripts & {sum(T.SCRIPT_BITS[s] for s in T.INDIC_SCRIPTS)}) > 0", 'other_script': f"((name_scripts | address_scripts) & {T.SCRIPT_BITS['Other']}) > 0",
    'parse_low': "address_parse_conf = 'low'", 'multi_postal': 'len(address_postal_candidates) > 1', 'repairs': "name_repairs <> ''",
}


# The script census (name_scan_counts.csv, other_script_rows) found no letter outside Latin and the nine Indic scripts in any of the 24.2M rows.
KNOWN_EMPTY_STRATA = frozenset({'other_script'})


def check_recompute(rep: Report, con, per_stratum: int = 250, modulus: int = 1500, extremes: int = 150, require_all_strata: bool = True) -> None:
    from normalization import comparison_key
    # Phase 1: pick the ids from the few columns each predicate needs (a sorted LIMIT over SELECT * would decode every column 27 times).
    picked: Dict[tuple, None] = {}

    def take(sql: str) -> None:
        for entity_id, split in con.execute(sql).fetchall():
            picked[(entity_id, split)] = None

    take(f"SELECT entity_id, split FROM f WHERE hash(entity_id) % {modulus} = 0")
    for cond in STRATA.values():
        take(f"SELECT entity_id, split FROM f WHERE {cond} ORDER BY hash(entity_id) LIMIT {per_stratum}")
    take(f"SELECT entity_id, split FROM f ORDER BY length(business_name) DESC, entity_id LIMIT {extremes}")
    take(f"SELECT entity_id, split FROM f ORDER BY length(business_address) DESC, entity_id LIMIT {extremes}")
    import pyarrow as pa
    con.register('sample_ids', pa.table({'entity_id': [k[0] for k in picked], 'split': [k[1] for k in picked]}))
    table = con.execute('SELECT f.* EXCLUDE (filename) FROM f JOIN sample_ids USING (entity_id, split)').fetch_arrow_table().to_pydict()
    con.unregister('sample_ids')
    n = len(table['entity_id'])
    record.clear_caches()
    mismatches, v1_bad, idem_bad = [], [], []
    for i in range(n):
        row = {c: table[c][i] for c in record.COLUMNS}
        want = dict(zip(record.COLUMNS, record.build_row(row['entity_id'], row['business_name'], row['business_address'], row['country'], row['name_key'],
                                                          row['address_key'], row['split'], row['source'], row['feature_version'], row['hygiene_version'])))
        diff = [c for c in record.COLUMNS if row[c] != want[c]]
        if diff:
            mismatches.append((row['entity_id'], diff[:4]))
        if comparison_key(row['business_name']) != row['name_key'] or comparison_key(row['business_address']) != row['address_key']:
            v1_bad.append(row['entity_id'])
        if row['address_canon'] and A.build_address_features(row['address_canon'], row['country'])['address_canon'] != row['address_canon']:
            idem_bad.append((row['entity_id'], 'address_canon'))
        if row['name_core'] and N.build_name_features(row['name_core'], row['country'])['name_core'] != row['name_core']:
            idem_bad.append((row['entity_id'], 'name_core'))
    rep.add('F1 stored rows == rows recomputed by the Python code, all 69 columns (hash sample + strata + extremes)', not mismatches,
            f'{n:,} rows compared; first mismatches: {mismatches[:3]}')
    rep.add('F2 v1 keys equal the frozen scripts/normalization.comparison_key on the same rows', not v1_bad, f'{n:,} rows; bad: {v1_bad[:3]}')
    rep.add('F3 address_canon and name_core are idempotent on the same rows', not idem_bad, f'bad: {idem_bad[:3]}')
    counts = {name: con.execute(f'SELECT count(*) FROM (SELECT 1 FROM f WHERE {cond} LIMIT 1)').fetchone()[0] for name, cond in STRATA.items()}
    empty = [k for k, v in counts.items() if not v]
    unexpected = [k for k in empty if k not in KNOWN_EMPTY_STRATA]
    rep.add('F4 every stratum is populated in the table (nothing untested because it is empty)' + ('' if require_all_strata else ' [informational on a sample build]'),
            not unexpected or not require_all_strata,
            f'{len(counts) - len(empty)}/{len(counts)} strata populated; empty: {empty}; known-empty by the script census: {sorted(KNOWN_EMPTY_STRATA)}')


# ------------------------------------------------------------------------------------------------------------------------------ G
def _file_hashes(base: Path) -> Dict[str, str]:
    return {p.relative_to(base).as_posix(): sha256_file(p) for p in sorted(base.rglob('*.parquet'))}


def check_determinism(rep: Report, con, root: Path, fdir: Path, manifest: dict, groups: int = 1, check_inputs: bool = True) -> None:
    import pyarrow.parquet as pq
    scratch = root / 'data' / 'features' / '_verify_scratch'
    if scratch.exists():
        shutil.rmtree(scratch)
    version = manifest['feature_version']
    quiet = lambda *_a, **_k: None
    try:
        first = pipeline.build(root, version, workers=2, max_groups=groups, log=quiet, out_base=scratch / 'a', check_inputs=check_inputs)
        second = pipeline.build(root, version, workers=5, max_groups=groups, log=quiet, out_base=scratch / 'b', check_inputs=check_inputs)
        same = _file_hashes(scratch / 'a' / version) == _file_hashes(scratch / 'b' / version)
        rep.add('G1 two scratch rebuilds (2 vs 5 workers, same row-group layout) are byte-identical, file by file', same,
                f'{first["manifest"]["totals"]["files"]} files, {first["manifest"]["totals"]["rows"]:,} rows')
        rep.add('G2 the two rebuilds record the same manifest', first['manifest'] == second['manifest'])
        third = pipeline.build(root, version, workers=4, max_groups=groups, flush_rows=7919, log=quiet, out_base=scratch / 'c', check_inputs=check_inputs)
        equal = True
        for rel in sorted(_file_hashes(scratch / 'a' / version)):
            equal &= pq.read_table(scratch / 'a' / version / rel).equals(pq.read_table(scratch / 'c' / version / rel))
        rep.add('G3 a rebuild with a different flush size (different row groups) has identical logical content', equal, f'{third["manifest"]["totals"]["rows"]:,} rows')
        glob_a = (scratch / 'a' / version / 'split=*' / 'source=*' / '*' / '*.parquet').as_posix()
        con.execute(f"CREATE OR REPLACE VIEW s AS SELECT * FROM read_parquet('{glob_a}', hive_partitioning=false)")
        cols = ', '.join(f'"{c}"' for c in record.COLUMNS)
        missing = con.execute(f"SELECT count(*) FROM (SELECT {cols} FROM s EXCEPT SELECT {cols} FROM f SEMI JOIN s USING (entity_id, split))").fetchone()[0]
        rep.add('G4 every row of the scratch rebuild equals the row stored in the built table (all columns)', missing == 0, f'{missing} differing rows')
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------------------------------ driver
def run_verification(root, version: str, determinism: bool = True, scans: Optional[bool] = None, threads: int = 8, echo: bool = True,
                     recompute: Optional[dict] = None) -> Report:
    root = Path(root)
    fdir = root / 'data' / 'features' / version
    rep = Report(echo)
    manifest = check_files(rep, root, fdir)
    full = not manifest['sample_build']
    con = connect(threads)
    register(con, fdir)
    check_coverage(rep, con, root, fdir, manifest)
    check_integrity(rep, con, fdir)
    check_invariants(rep, con, manifest['feature_version'])
    if (full if scans is None else scans):
        check_scans(rep, con, root)
    check_recompute(rep, con, require_all_strata=full, **(recompute or {}))
    if determinism:
        check_determinism(rep, con, root, fdir, manifest, check_inputs=(root / 'manifests' / 'input_manifest_v1.json').exists())
    return rep
