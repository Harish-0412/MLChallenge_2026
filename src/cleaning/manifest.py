"""Phase 1: input manifest and ingestion guard rails.

The manifest proves, from three independent readers, that every input row is accounted for:

1. a strict streaming Python ``csv`` parse of the raw TSV (this module),
2. the DuckDB strict parse of the same raw TSV (same options as ``scripts/audit_dataset.py``),
3. the Parquet copies in ``data/interim/`` used by all later work.

Counts, per-country counts, code-point lengths and an order-independent content hash must agree. The manifest is
deterministic (no timestamps or timings; those go in a separate run record), so its SHA-256 is a stable identifier
that later outputs can record.
"""
import csv
import hashlib
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MANIFEST_VERSION = 'input_manifest_v1'
DATASET_DIR = 'student_resource/dataset'
SOURCE_COLUMNS = ['entity_id', 'business_name', 'business_address', 'country']
TRUTH_COLUMNS = ['source1_entity_id', 'matched_entity_ids']

# name -> path relative to the dataset directory. This is the only set of files the pipeline may read as data.
ALLOWLIST: Dict[str, str] = {
    'train_source1': 'train/train_source1.tsv',
    'train_source2': 'train/train_source2.tsv',
    'train_source3': 'train/train_source3.tsv',
    'train_ground_truth': 'train/train_ground_truth.tsv',
    'test_source1': 'test/test_source1.tsv',
    'test_source2': 'test/test_source2.tsv',
    'test_source3': 'test/test_source3.tsv',
}
SOURCE_TABLES = [n for n in ALLOWLIST if n != 'train_ground_truth']
FORBIDDEN_COMPONENTS = {'__MACOSX', '.venv', '__pycache__', 'reports', 'data', 'tmp', '.git', 'manifests', 'output'}
METADATA_NAMES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}
DATA_SUFFIXES = {'.tsv', '.csv', '.txt', '.parquet', '.json', '.jsonl'}
_ID_RE = re.compile(r'S[123]-[0-9]+')


class DatasetDiscoveryError(RuntimeError):
    """A path that is not on the dataset allowlist, or that looks like metadata/output, was offered as data."""


class MalformedInputError(RuntimeError):
    """A structural problem in an input file, reported with its location."""

    def __init__(self, path, line: int, reason: str):
        super().__init__(f'{path}: line {line}: {reason}')
        self.path, self.line, self.reason = str(path), line, reason


class ManifestReconciliationError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------------- discovery guard
def _is_metadata(name: str) -> bool:
    return name.startswith('._') or name in METADATA_NAMES


def discovery_guard(path, dataset_root) -> Path:
    """Return the resolved path only if it is exactly one of the allowlisted dataset files."""
    root = Path(dataset_root).resolve()
    resolved = Path(path).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise DatasetDiscoveryError(f'{path} is outside the dataset directory {root}') from None
    for part in relative.parts:
        if part in FORBIDDEN_COMPONENTS or _is_metadata(part):
            raise DatasetDiscoveryError(f'{path}: component {part!r} is metadata, output or environment, never data')
    if relative.as_posix() not in ALLOWLIST.values():
        raise DatasetDiscoveryError(f'{path} is not on the seven-file allowlist')
    return resolved


def resolve_allowlist(project_root) -> Tuple[Dict[str, Path], List[str]]:
    """Locate the seven allowlisted files; list (but never read) everything else under the dataset directory.

    Raises if an unlisted data-looking file is present, so that a stray output or report cannot be picked up silently.
    """
    dataset_root = Path(project_root) / DATASET_DIR
    if not dataset_root.is_dir():
        raise DatasetDiscoveryError(f'dataset directory missing: {dataset_root}')
    found: Dict[str, Path] = {}
    for name, relative in ALLOWLIST.items():
        path = dataset_root / relative
        if not path.is_file():
            raise DatasetDiscoveryError(f'allowlisted file missing: {path}')
        found[name] = discovery_guard(path, dataset_root)
    excluded: List[str] = []
    allowed = set(ALLOWLIST.values())
    for folder, _dirs, files in os.walk(dataset_root):
        for file_name in files:
            relative = (Path(folder) / file_name).relative_to(dataset_root).as_posix()
            if relative in allowed:
                continue
            if not _is_metadata(file_name) and Path(file_name).suffix.lower() in DATA_SUFFIXES:
                raise DatasetDiscoveryError(f'unlisted data-like file in the dataset directory: {relative}')
            excluded.append(relative)
    return found, sorted(excluded)


def sha256_file(path) -> str:
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


# --------------------------------------------------------------------------------------------- python profile
class _LineCounter:
    """Iterates text lines while counting physical lines, lines with a double quote and CRLF endings."""

    def __init__(self, stream):
        self.stream, self.lines, self.quote_lines, self.crlf_lines = stream, 0, 0, 0

    def __iter__(self):
        return self

    def __next__(self):
        line = next(self.stream)
        self.lines += 1
        if '"' in line:
            self.quote_lines += 1
        if line.endswith('\r\n'):
            self.crlf_lines += 1
        return line


def _reader(path):
    """Strict UTF-8 text stream plus a strict quote-aware csv reader (same quoting rules as the DuckDB parse)."""
    with open(path, 'rb') as raw:
        has_bom = raw.read(3) == b'\xef\xbb\xbf'
    stream = open(path, encoding='utf-8', errors='strict', newline='')
    counter = _LineCounter(stream)
    reader = csv.reader(counter, delimiter='\t', quotechar='"', doublequote=True, strict=True)
    return stream, counter, reader, has_bom


def profile_tsv(path, columns: List[str], kind: str = 'source', source_number: Optional[int] = None) -> dict:
    """Streaming, strict profile of one TSV. Raises MalformedInputError with the location of the first structural fault."""
    stream, counter, reader, has_bom = _reader(path)
    try:
        try:
            header = next(reader)
        except StopIteration:
            raise MalformedInputError(path, 0, 'empty file') from None
        except (csv.Error, UnicodeDecodeError) as error:
            raise MalformedInputError(path, reader.line_num, f'unreadable header: {error}') from None
        if header and has_bom:
            header[0] = header[0].lstrip('﻿')
        if header != columns:
            raise MalformedInputError(path, 1, f'header {header!r} != expected {columns!r}')
        if kind == 'source':
            return _profile_source_rows(path, reader, counter, columns, source_number, has_bom)
        return _profile_truth_rows(path, reader, counter, columns, has_bom)
    finally:
        stream.close()


def _rows(path, reader):
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except UnicodeDecodeError as error:
            raise MalformedInputError(path, reader.line_num, f'invalid UTF-8: {error}') from None
        except csv.Error as error:
            raise MalformedInputError(path, reader.line_num, f'csv error: {error}') from None


def _profile_source_rows(path, reader, counter, columns, source_number, has_bom) -> dict:
    prefix = f'S{source_number}-' if source_number else None
    ids = set()
    add_id = ids.add
    countries: Dict[str, List[int]] = {}
    rows = quote_rows = bad_format = bad_prefix = 0
    empty_name = empty_address = empty_country = 0
    name_chars = address_chars = max_name = max_address = 0
    width = len(columns)
    for row in _rows(path, reader):
        if len(row) != width:
            raise MalformedInputError(path, reader.line_num, f'{len(row)} fields, expected {width}')
        entity_id, name, address, country = row
        rows += 1
        add_id(entity_id)
        if not _ID_RE.fullmatch(entity_id):
            bad_format += 1
        if prefix and not entity_id.startswith(prefix):
            bad_prefix += 1
        if '"' in name or '"' in address or '"' in country:
            quote_rows += 1
        blank_address = address.strip() == ''
        empty_name += name.strip() == ''
        empty_address += blank_address
        empty_country += country.strip() == ''
        name_chars += len(name)
        address_chars += len(address)
        max_name = max(max_name, len(name))
        max_address = max(max_address, len(address))
        entry = countries.get(country)
        if entry is None:
            entry = countries[country] = [0, 0]
        entry[0] += 1
        entry[1] += blank_address
    return {
        'rows': rows, 'physical_lines': counter.lines, 'lines_with_double_quote': counter.quote_lines,
        'crlf_lines': counter.crlf_lines, 'has_bom': has_bom, 'rows_with_quote_char_in_value': quote_rows,
        'distinct_ids': len(ids), 'id_format_violations': bad_format, 'id_prefix_violations': bad_prefix,
        'empty_name_after_strip': empty_name, 'empty_address_after_strip': empty_address,
        'empty_country_after_strip': empty_country,
        'name_codepoints': name_chars, 'address_codepoints': address_chars,
        'max_name_length': max_name, 'max_address_length': max_address,
        'per_country': {c: {'rows': v[0], 'blank_address': v[1]} for c, v in sorted(countries.items())},
    }


def _profile_truth_rows(path, reader, counter, columns, has_bom) -> dict:
    s1_ids = set()
    rows = empty = links = bad_s1 = bad_target = dup_in_list = max_len = 0
    lengths: Counter = Counter()
    for row in _rows(path, reader):
        if len(row) != len(columns):
            raise MalformedInputError(path, reader.line_num, f'{len(row)} fields, expected {len(columns)}')
        s1_id, matched = row
        rows += 1
        s1_ids.add(s1_id)
        if not re.fullmatch(r'S1-[0-9]+', s1_id):
            bad_s1 += 1
        items = matched.split(',') if matched else []
        empty += not items
        lengths[len(items)] += 1
        max_len = max(max_len, len(items))
        links += len(items)
        if len(set(items)) != len(items):
            dup_in_list += 1
        bad_target += sum(1 for i in items if not re.fullmatch(r'S[23]-[0-9]+', i))
    return {
        'rows': rows, 'physical_lines': counter.lines, 'lines_with_double_quote': counter.quote_lines,
        'crlf_lines': counter.crlf_lines, 'has_bom': has_bom,
        'distinct_source1_ids': len(s1_ids), 'source1_id_format_violations': bad_s1,
        'rows_with_no_matches': empty, 'positive_links': links, 'target_id_format_violations': bad_target,
        'rows_with_duplicate_ids_in_list': dup_in_list, 'max_matches_per_row': max_len,
        'match_count_distribution': {str(k): v for k, v in sorted(lengths.items())},
    }


def _profile_task(task):
    """Process-pool entry point. Returns the profile plus the worker's own timing and peak memory."""
    import psutil
    name, path, columns, kind, source_number = task
    started = time.perf_counter()
    result = profile_tsv(path, columns, kind, source_number)
    info = psutil.Process().memory_info()
    return name, result, {'seconds': round(time.perf_counter() - started, 2),
                          'peak_memory_mb': round(getattr(info, 'peak_wset', info.rss) / 2 ** 20)}


def _run_tasks(tasks, workers: int):
    """Run profile tasks in worker processes, or in-process when workers <= 1 (used by tests)."""
    if workers <= 1:
        yield from map(_profile_task, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(_profile_task, tasks)


# --------------------------------------------------------------------------------------------- duckdb profile
def _literal(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def duckdb_csv_scan(path, columns: List[str]) -> str:
    """Identical parse options to scripts/audit_dataset.csv_scan (asserted equal in the tests)."""
    schema = '{' + ','.join(f"{_literal(k)}:'VARCHAR'" for k in columns) + '}'
    return f"""read_csv({_literal(Path(path).as_posix())}, delim='\t', header=true,
        columns={schema}, auto_detect=false, quote='"', escape='"',
        force_not_null=[{','.join(_literal(k) for k in columns)}],
        strict_mode=true, ignore_errors=false, null_padding=false)"""


def duckdb_profile(con, relation: str) -> dict:
    """Same quantities as the Python profile (row count, distinct IDs, code points, blanks) plus a content hash."""
    total = con.execute(f"""SELECT count(*), count(DISTINCT entity_id), sum(length(business_name)), sum(length(business_address)),
        count_if(trim(business_name)=''), count_if(trim(business_address)=''), count_if(trim(country)=''),
        sum(hash(entity_id, business_name, business_address, country))::HUGEINT FROM {relation}""").fetchone()
    countries = con.execute(f"""SELECT country, count(*), count_if(trim(business_address)='') FROM {relation}
        GROUP BY country ORDER BY country""").fetchall()
    return {'rows': total[0], 'distinct_ids': total[1], 'name_codepoints': int(total[2] or 0),
            'address_codepoints': int(total[3] or 0), 'empty_name_after_trim': total[4],
            'empty_address_after_trim': total[5], 'empty_country_after_trim': total[6],
            'content_hash_sum': str(total[7]),
            'per_country': {c: {'rows': n, 'blank_address': b} for c, n, b in countries}}


def label_integrity(con, truth_path, root: Path) -> dict:
    """Ground-truth checks derived from the raw truth TSV and the Parquet copies (independent of audit.duckdb)."""
    interim = root / 'data' / 'interim'
    s1 = _literal((interim / 'train_source1.parquet').as_posix())
    s2 = _literal((interim / 'train_source2.parquet').as_posix())
    s3 = _literal((interim / 'train_source3.parquet').as_posix())
    con.execute(f'CREATE OR REPLACE TEMP TABLE truth_rows AS SELECT * FROM {duckdb_csv_scan(truth_path, TRUTH_COLUMNS)}')
    con.execute("""CREATE OR REPLACE TEMP TABLE truth_pairs AS SELECT source1_entity_id,
        unnest(string_split(matched_entity_ids, ',')) AS target_id FROM truth_rows WHERE matched_entity_ids<>''""")
    one = lambda sql: con.execute(sql).fetchone()[0]
    return {
        'rows': one('SELECT count(*) FROM truth_rows'),
        'distinct_source1_ids': one('SELECT count(DISTINCT source1_entity_id) FROM truth_rows'),
        'source1_ids_missing_from_truth': one(f'SELECT count(*) FROM read_parquet({s1}) s ANTI JOIN truth_rows g ON s.entity_id=g.source1_entity_id'),
        'truth_ids_unknown_in_train_source1': one(f'SELECT count(*) FROM truth_rows g ANTI JOIN read_parquet({s1}) s ON s.entity_id=g.source1_entity_id'),
        'positive_links': one('SELECT count(*) FROM truth_pairs'),
        'duplicate_pairs': one('SELECT count(*)-count(DISTINCT (source1_entity_id,target_id)) FROM truth_pairs'),
        'targets_with_multiple_source1_owners': one('SELECT count(*) FROM (SELECT target_id FROM truth_pairs GROUP BY target_id HAVING count(DISTINCT source1_entity_id)>1)'),
        'targets_missing_from_train_source2_source3': one(f"""SELECT count(*) FROM truth_pairs p ANTI JOIN
            (SELECT entity_id FROM read_parquet({s2}) UNION ALL SELECT entity_id FROM read_parquet({s3})) t ON p.target_id=t.entity_id"""),
        'links_with_country_mismatch': one(f"""SELECT count(*) FROM truth_pairs p JOIN read_parquet({s1}) a ON p.source1_entity_id=a.entity_id
            JOIN (SELECT entity_id, country FROM read_parquet({s2}) UNION ALL SELECT entity_id, country FROM read_parquet({s3})) t
            ON p.target_id=t.entity_id WHERE a.country<>t.country"""),
        'links_to_source2': one("SELECT count(*) FROM truth_pairs WHERE starts_with(target_id,'S2-')"),
        'links_to_source3': one("SELECT count(*) FROM truth_pairs WHERE starts_with(target_id,'S3-')"),
    }


# --------------------------------------------------------------------------------------------- build
def _check(problems: List[str], condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def build_manifest(project_root, workers: int = 4, duckdb_memory: str = '4GB', duckdb_threads: int = 4,
                   log=print) -> Tuple[dict, dict]:
    """Build the deterministic manifest and a separate (non-deterministic) run record. Raises if anything disagrees."""
    import duckdb
    root = Path(project_root)
    started = time.perf_counter()
    paths, excluded = resolve_allowlist(root)
    audit = json.loads((root / 'reports' / 'eda' / 'full_audit.json').read_text(encoding='utf-8'))
    audit_files = {Path(item['file'].replace('\\', '/')).as_posix(): item for item in audit['files']}
    log('hashing inputs')
    files: Dict[str, dict] = {}
    for name, path in paths.items():
        files[name] = {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}

    log(f'strict Python parse with {workers} workers')
    tasks = []
    for name in ALLOWLIST:
        if name == 'train_ground_truth':
            tasks.append((name, str(paths[name]), TRUTH_COLUMNS, 'truth', None))
        else:
            tasks.append((name, str(paths[name]), SOURCE_COLUMNS, 'source', int(name[-1])))
    tasks.sort(key=lambda t: -files[t[0]]['bytes'])  # largest first
    worker_info: Dict[str, dict] = {}
    for name, result, info in _run_tasks(tasks, workers):
        files[name]['python_parse'] = result
        worker_info[name] = info
        log(f'  {name}: {result["rows"]:,} rows in {info["seconds"]}s, peak {info["peak_memory_mb"]} MB')

    log('DuckDB parse of the raw TSVs and of the Parquet copies')
    con = duckdb.connect()
    con.execute(f'SET memory_limit={_literal(duckdb_memory)}')
    con.execute(f'SET threads={int(duckdb_threads)}')
    con.execute('SET preserve_insertion_order=false')
    duckdb_seconds = {}
    for name in SOURCE_TABLES:
        t0 = time.perf_counter()
        files[name]['duckdb_raw_parse'] = duckdb_profile(con, duckdb_csv_scan(paths[name], SOURCE_COLUMNS))
        parquet = root / 'data' / 'interim' / f'{name}.parquet'
        files[name]['parquet_copy'] = duckdb_profile(con, f'read_parquet({_literal(parquet.as_posix())})')
        files[name]['parquet_copy']['path'] = parquet.relative_to(root).as_posix()
        duckdb_seconds[name] = round(time.perf_counter() - t0, 2)
        log(f'  {name}: done in {duckdb_seconds[name]}s')
    log('label integrity')
    labels = label_integrity(con, paths['train_ground_truth'], root)
    con.close()

    # ---------------------------------------------------------------- reconciliation
    problems: List[str] = []
    checks = {'sha256_and_bytes_equal_audit': True, 'python_equals_duckdb_raw': True, 'duckdb_raw_equals_parquet': True,
              'per_country_rows_equal_audit': True, 'no_structural_anomalies': True}
    for name in SOURCE_TABLES:
        f = files[name]
        py, raw, pq = f['python_parse'], f['duckdb_raw_parse'], f['parquet_copy']
        rel = Path(f['path']).relative_to(DATASET_DIR).as_posix()
        recorded = next((v for k, v in audit_files.items() if k.endswith(rel)), None)
        ok = recorded is not None and recorded['sha256'] == f['sha256'] and recorded['bytes'] == f['bytes']
        checks['sha256_and_bytes_equal_audit'] &= ok
        _check(problems, ok, f'{name}: sha256/bytes differ from full_audit.json')
        same_py_duck = all([py['rows'] == raw['rows'], py['distinct_ids'] == raw['distinct_ids'],
                            py['name_codepoints'] == raw['name_codepoints'], py['address_codepoints'] == raw['address_codepoints'],
                            py['per_country'] == raw['per_country'],
                            py['empty_name_after_strip'] == raw['empty_name_after_trim'],
                            py['empty_address_after_strip'] == raw['empty_address_after_trim'],
                            py['empty_country_after_strip'] == raw['empty_country_after_trim']])
        checks['python_equals_duckdb_raw'] &= same_py_duck
        _check(problems, same_py_duck, f'{name}: Python and DuckDB parses of the raw TSV disagree')
        same_raw_pq = {k: v for k, v in raw.items()} == {k: v for k, v in pq.items() if k != 'path'}
        checks['duckdb_raw_equals_parquet'] &= same_raw_pq
        _check(problems, same_raw_pq, f'{name}: Parquet copy differs from the raw TSV (rows, hash, lengths or countries)')
        audit_rows = {r['country']: (r['rows'], r['missing_address']) for r in audit['profiles'][name]}
        mine = {c: (v['rows'], v['blank_address']) for c, v in py['per_country'].items()}
        checks['per_country_rows_equal_audit'] &= audit_rows == mine
        _check(problems, audit_rows == mine, f'{name}: per-country rows/blank addresses differ from the audit')
        clean = all([py['physical_lines'] == py['rows'] + 1, py['id_format_violations'] == 0, py['id_prefix_violations'] == 0,
                     py['distinct_ids'] == py['rows'], py['empty_name_after_strip'] == 0, py['empty_country_after_strip'] == 0,
                     not py['has_bom'], py['crlf_lines'] == 0 or py['crlf_lines'] >= py['physical_lines'] - 1])
        checks['no_structural_anomalies'] &= clean
        _check(problems, clean, f'{name}: structural anomaly (multi-line rows, bad IDs, duplicates, blank name/country, BOM)')
    truth = files['train_ground_truth']['python_parse']
    truth_audit = audit['truth_integrity']
    _check(problems, truth['rows'] == labels['rows'] == truth_audit['rows'], 'ground-truth row count disagrees')
    _check(problems, truth['positive_links'] == labels['positive_links'] == truth_audit['positive_links'], 'positive link count disagrees')
    _check(problems, truth['distinct_source1_ids'] == truth['rows'], 'ground truth has duplicate Source 1 rows')
    for key in ['source1_ids_missing_from_truth', 'truth_ids_unknown_in_train_source1', 'duplicate_pairs',
                'targets_with_multiple_source1_owners', 'targets_missing_from_train_source2_source3', 'links_with_country_mismatch']:
        _check(problems, labels[key] == 0, f'label integrity: {key} = {labels[key]}')
    _check(problems, files['train_ground_truth']['python_parse']['physical_lines'] == truth['rows'] + 1, 'ground truth has multi-line rows')
    if problems:
        raise ManifestReconciliationError('\n'.join(problems))

    totals = {'source_rows': sum(files[n]['python_parse']['rows'] for n in SOURCE_TABLES),
              'label_rows': truth['rows'], 'positive_links': truth['positive_links']}
    manifest = {
        'manifest_version': MANIFEST_VERSION,
        'dataset_directory': DATASET_DIR,
        'source_columns': SOURCE_COLUMNS, 'truth_columns': TRUTH_COLUMNS,
        'allowlist': ALLOWLIST,
        'excluded_files_never_read': excluded,
        'parser': {'python': "csv.reader(delimiter='\\t', quotechar='\"', doublequote=True, strict=True), UTF-8 strict",
                   'duckdb': 'read_csv delim=TAB, quote/escape=", strict_mode=true, ignore_errors=false, all VARCHAR, no NULL conversion'},
        'files': files, 'label_integrity': labels, 'totals': totals,
        'reconciliation': checks,
    }
    run = {'seconds_total': round(time.perf_counter() - started, 2), 'workers': workers,
           'python_parse_workers': worker_info, 'duckdb_seconds': duckdb_seconds,
           'duckdb_memory_limit': duckdb_memory, 'duckdb_threads': duckdb_threads}
    return manifest, run


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def manifest_sha256(path) -> str:
    return sha256_file(path)


def assert_inputs_match_manifest(project_root, manifest_path) -> None:
    """Cheap guard for later phases: the seven input files on disk must equal the recorded size and SHA-256."""
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    paths, _ = resolve_allowlist(project_root)
    for name, path in paths.items():
        recorded = manifest['files'][name]
        if path.stat().st_size != recorded['bytes'] or sha256_file(path) != recorded['sha256']:
            raise ManifestReconciliationError(f'{name}: input file changed since the manifest was built')
