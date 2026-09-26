"""Phase 6: parallel, deterministic, refuse-to-overwrite feature build.

    data/features/<version>/split=<train|test>/source=<1|2|3>/country=<label>/part-<table>-<first row group>.parquet
    data/features/<version>/_manifest.json     deterministic: versions, hashes, schema, partitions, row counts, bytes
    data/features/<version>/_run.json          run-specific: timings, memory, libraries, command line

A task = a few consecutive row groups of one input Parquet copy. A worker streams them, builds every record with
``record.build_row`` and writes one part file per country (hive partition values are URL-quoted, so any country label is legal).
The build goes to ``<version>.tmp`` and is renamed on success, so an interrupted run can never be mistaken for a finished version,
and an existing version directory is never overwritten.
"""
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
from urllib.parse import quote

from . import HYGIENE_VERSION
from .lexicons import all_lexicon_hashes
from .manifest import SOURCE_TABLES, assert_inputs_match_manifest, sha256_file

FLUSH_ROWS = 50_000
GROUPS_PER_TASK = 2


class Task(NamedTuple):
    table: str
    path: str
    groups: tuple
    split: str
    source: int
    out_root: str
    version: str
    flush_rows: int


# Code that only CHECKS a finished table never changes it, so editing it must not invalidate the table's recorded source hash.
VERIFICATION_ONLY = frozenset({'feature_verify.py', 'hygiene_scan.py', 'name_scan.py'})


def source_tree_hash(root: Path) -> str:
    """SHA-256 over every source file that defines the features (code and lexicons; the project is not a git repository)."""
    digest = hashlib.sha256()
    base = root / 'src' / 'cleaning'
    for path in sorted(list(base.rglob('*.py')) + list(base.rglob('*.tsv'))):
        if path.name in VERIFICATION_ONLY:
            continue
        digest.update(path.relative_to(base).as_posix().encode('utf-8'))
        digest.update(sha256_file(path).encode('ascii'))
    return digest.hexdigest()


def partition_dir(out_root: Path, split: str, source: int, country: str) -> Path:
    return out_root / f'split={split}' / f'source={source}' / f'country={quote(country, safe="")}'


def plan_tasks(root: Path, out_root: Path, version: str, max_groups: int = 0, flush_rows: int = FLUSH_ROWS) -> List[Task]:
    import pyarrow.parquet as pq
    tasks = []
    for table in SOURCE_TABLES:
        path = root / 'data' / 'interim' / f'{table}.parquet'
        total = pq.ParquetFile(path).num_row_groups
        groups = list(range(total if not max_groups else min(total, max_groups)))
        split, source = table.split('_source')[0], int(table[-1])
        for start in range(0, len(groups), GROUPS_PER_TASK):
            tasks.append(Task(table, str(path), tuple(groups[start:start + GROUPS_PER_TASK]), split, source, str(out_root), version, flush_rows))
    return tasks


def process_task(task: Task) -> dict:
    """Process-pool entry point. Returns statistics only; all data goes to disk."""
    import psutil
    import pyarrow as pa
    import pyarrow.parquet as pq
    from . import record

    started = time.perf_counter()
    parquet = pq.ParquetFile(task.path)
    out_root = Path(task.out_root)
    buffers: Dict[str, List[list]] = {}
    writers: Dict[str, pq.ParquetWriter] = {}
    written: Dict[str, dict] = {}

    def flush(country: str) -> None:
        columns = buffers[country]
        if not columns[0]:
            return
        writer = writers.get(country)
        if writer is None:
            directory = partition_dir(out_root, task.split, task.source, country)
            directory.mkdir(parents=True, exist_ok=True)
            name = f'part-{task.table}-{task.groups[0]:04d}.parquet'
            writer = writers[country] = pq.ParquetWriter(directory / name, record.SCHEMA, compression='zstd')
            written[country] = {'path': (directory / name).relative_to(out_root).as_posix(), 'rows': 0}
        arrays = [pa.array(values, type=field.type) for values, field in zip(columns, record.SCHEMA)]
        writer.write_table(pa.Table.from_arrays(arrays, schema=record.SCHEMA))
        written[country]['rows'] += len(columns[0])
        for values in columns:
            values.clear()

    rows = 0
    for group in task.groups:
        data = parquet.read_row_group(group, columns=list(record.INPUT_COLUMNS)).to_pydict()
        for entity_id, name, address, country, name_key, address_key in zip(*(data[c] for c in record.INPUT_COLUMNS)):
            values = record.build_row(entity_id, name, address, country, name_key, address_key, task.split, task.source, task.version, HYGIENE_VERSION)
            columns = buffers.get(country)
            if columns is None:
                columns = buffers[country] = [[] for _ in record.COLUMNS]
            for target, value in zip(columns, values):
                target.append(value)
            if len(columns[0]) >= task.flush_rows:
                flush(country)
            rows += 1
    for country in list(buffers):
        flush(country)
    for writer in writers.values():
        writer.close()
    files = []
    for country, info in sorted(written.items()):
        info = dict(info, country=country, bytes=(out_root / info['path']).stat().st_size)
        files.append(info)
    memory = psutil.Process().memory_info()
    return {'table': task.table, 'groups': list(task.groups), 'rows': rows, 'files': files, 'seconds': round(time.perf_counter() - started, 2),
            'peak_memory_mb': round(getattr(memory, 'peak_wset', memory.rss) / 2 ** 20)}


def build(root, version: str, workers: int = 6, max_groups: int = 0, flush_rows: int = FLUSH_ROWS, log=lambda m: print(m, flush=True), command: Optional[List[str]] = None,
          out_base=None, check_inputs: bool = True) -> dict:
    """Build a feature version. Refuses to overwrite; verifies the inputs against the input manifest first (``check_inputs=False`` is for
    unit tests on synthetic inputs only). ``out_base`` (default <root>/data/features) lets verification rebuild into a scratch directory."""
    root = Path(root)
    final = (Path(out_base) if out_base else root / 'data' / 'features') / version
    tmp = final.with_name(version + '.tmp')
    if final.exists():
        raise FileExistsError(f'{final} already exists: a validated feature version is never overwritten (choose a new version name)')
    input_manifest = root / 'manifests' / 'input_manifest_v1.json'
    if check_inputs:
        assert_inputs_match_manifest(root, input_manifest)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    tasks = plan_tasks(root, tmp, version, max_groups, flush_rows)
    log(f'{len(tasks)} tasks, {workers} workers -> {final}')
    started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, result in enumerate(pool.map(process_task, tasks, chunksize=1), 1):
            results.append(result)
            if i % 10 == 0 or i == len(tasks):
                log(f'  {i}/{len(tasks)} tasks, {sum(r["rows"] for r in results):,} rows, {time.perf_counter() - started:.0f}s')
    wall = time.perf_counter() - started

    from . import record
    partitions: Dict[tuple, dict] = {}
    for r in results:
        source = int(r['table'][-1])
        split = r['table'].split('_source')[0]
        for f in r['files']:
            key = (split, source, f['country'])
            entry = partitions.setdefault(key, {'split': split, 'source': source, 'country': f['country'],
                                                'directory': partition_dir(Path('.'), split, source, f['country']).as_posix(), 'rows': 0, 'bytes': 0, 'files': []})
            entry['rows'] += f['rows']
            entry['bytes'] += f['bytes']
            entry['files'].append({'path': f['path'], 'rows': f['rows'], 'bytes': f['bytes']})
    for entry in partitions.values():
        entry['files'].sort(key=lambda x: x['path'])
    ordered = [partitions[k] for k in sorted(partitions)]
    manifest = {
        'feature_version': version, 'hygiene_version': HYGIENE_VERSION,
        'sample_build': bool(max_groups), 'max_row_groups_per_table': max_groups,
        'input_manifest_sha256': sha256_file(input_manifest) if input_manifest.exists() else '', 'source_tree_sha256': source_tree_hash(root), 'lexicon_sha256': all_lexicon_hashes(),
        'schema': [{'name': f.name, 'type': str(f.type)} for f in record.SCHEMA],
        'partitions': ordered, 'totals': {'rows': sum(p['rows'] for p in ordered), 'bytes': sum(p['bytes'] for p in ordered), 'files': sum(len(p['files']) for p in ordered)},
        'reading': "duckdb: read_parquet('data/features/<version>/**/*.parquet', hive_partitioning=true)",
    }
    import duckdb, pyarrow, psutil
    run = {'created_unix': int(time.time()), 'wall_seconds': round(wall, 1), 'workers': workers, 'flush_rows': flush_rows, 'groups_per_task': GROUPS_PER_TASK,
           'cpu_seconds_in_workers': round(sum(r['seconds'] for r in results), 1), 'peak_worker_memory_mb': max(r['peak_memory_mb'] for r in results),
           'rows_per_second_wall': round(manifest['totals']['rows'] / wall), 'python': platform.python_version(), 'platform': platform.platform(),
           'duckdb': duckdb.__version__, 'pyarrow': pyarrow.__version__, 'psutil': psutil.__version__, 'command': command or sys.argv}
    (tmp / '_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    (tmp / '_run.json').write_text(json.dumps(run, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    os.replace(tmp, final)
    return {'manifest': manifest, 'run': run}
