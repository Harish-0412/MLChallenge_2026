"""Phase 2 verification over ALL rows of the six Parquet copies.

    python scripts/hygiene_report.py                 # full scan, writes reports/cleaning/*
    python scripts/hygiene_report.py --max-groups 3  # quick smoke run (prints only; writes nothing)

Outputs (reports/cleaning/): hygiene_change_counts.csv, hygiene_verification.json, hygiene_examples.md,
ftfy_experiment.md. Exit code 0 only if every acceptance check passes.
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from cleaning import hygiene_scan as scan  # noqa: E402
from cleaning import text_hygiene as h  # noqa: E402
from cleaning.lexicons import read_lexicon, lexicon_sha256  # noqa: E402
from cleaning.manifest import SOURCE_TABLES  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'
INTERIM = ROOT / 'data' / 'interim'
AUDIT_METRICS = {  # metric here -> field in reports/eda/full_audit.json profiles (an independent SQL computation)
    'rows': 'rows', 'flag:address_missing': 'missing_address', 'flag:name_multispace': 'name_repeated_whitespace',
    'flag:address_multispace': 'address_repeated_whitespace', 'flag:any_control': 'control_character_rows',
    'flag:any_format': 'format_character_rows',
}


def tasks(max_groups):
    import pyarrow.parquet as pq
    out = []
    for table in SOURCE_TABLES:
        path = INTERIM / f'{table}.parquet'
        groups = pq.ParquetFile(path).num_row_groups
        out += [(table, str(path), g) for g in range(groups if not max_groups else min(groups, max_groups))]
    return out


def audit_comparison(counts, audit):
    rows = []
    for table in SOURCE_TABLES:
        for profile in audit['profiles'][table]:
            for metric, audit_key in AUDIT_METRICS.items():
                mine = counts.get((table, profile['country'], metric), 0)
                theirs = profile[audit_key]
                rows.append({'table': table, 'country': profile['country'], 'metric': metric, 'mine': mine,
                             'audit_sql': theirs, 'equal': mine == theirs})
    return rows


def dotted_check(census, full=True):
    lexicon = {r['collapsed']: int(r['observed_count']) for r in read_lexicon('legal_dotted.tsv')}
    listed = {f: {'recorded': lexicon[f], 'census': census.get(f, 0), 'equal': lexicon[f] == census.get(f, 0)} for f in sorted(lexicon)}
    excluded = {r['collapsed']: int(r['observed_count']) for r in read_lexicon('dotted_excluded.tsv')}
    assert not set(excluded) & set(lexicon), 'a reviewed exclusion must not also be in the join lexicon'
    missed = {f: n for f, n in census.most_common() if f not in lexicon and f not in excluded and n >= 200}
    stale = {f: {'recorded': n, 'census': census.get(f, 0)} for f, n in excluded.items() if census.get(f, 0) != n}
    assert not (stale and full), f'dotted_excluded.tsv counts differ from the census: {stale}'   # a partial smoke scan sees a partial census
    return listed, missed


def ftfy_experiment(flagged, sample):
    """Bounded experiment: is ftfy needed, and is it safe to run globally? Compares with the narrow rule."""
    import ftfy
    lines = ['# ftfy experiment (bounded, experiment only)', '',
             f'ftfy {ftfy.__version__}, default `fix_text` settings. Compared with the narrow rule `text_hygiene.clean_text`.', '']
    fields = [(t, e, kind, raw) for t, e, n, a in flagged for kind, raw in (('name', n), ('address', a)) if h.has_control(raw) or h.has_mojibake(raw)]
    equal = differ = unchanged = 0
    shapes = Counter()
    examples = []
    for table, eid, kind, raw in fields:
        ours = h.lmn_key(h.clean_text(raw)[0])
        theirs_text = ftfy.fix_text(raw)
        theirs = h.lmn_key(theirs_text)
        shape = ('A-circ+C1' if 'Â' in raw and any('\x80' <= c <= '\x9f' for c in raw) else
                 'a-circ+C1' if 'â' in raw and any('\x80' <= c <= '\x9f' for c in raw) else
                 'SUB' if '\x1a' in raw else 'other control')
        shapes[shape] += 1
        if theirs_text == raw:
            unchanged += 1
        if ours == theirs:
            equal += 1
        else:
            differ += 1
            if len(examples) < 8:
                examples.append((table, eid, kind, shape, raw, h.clean_text(raw)[0], theirs_text))
    lines += [f'## Flagged fields (control/C1/SUB), {len(fields):,} fields in all six files', '',
              f'- ftfy result equals the narrow rule after the v1 key: **{equal:,}**; differs: **{differ:,}**; ftfy left the string unchanged: **{unchanged:,}**.',
              f'- Shapes: {dict(shapes)}', '']
    for table, eid, kind, shape, raw, ours, theirs in examples:
        lines.append(f'- `{table}` {eid} ({kind}, {shape}): raw `{raw!r}`; narrow rule `{ours!r}`; ftfy `{theirs!r}`')
    changed = Counter()
    n_fields = n_changed = 0
    for table, eid, name, address in sample:
        for raw in (name, address):
            n_fields += 1
            out = ftfy.fix_text(raw)
            if out != raw:
                n_changed += 1
                for c in set(raw) - set(out):
                    changed[c] += 1
    lines += ['', '## Why ftfy and the narrow rule differ',
              '', 'In the differing rows U+001A is a *substituted apostrophe* (`Noor` + U+001A + `S Complex`, meaning "Noor\'s Complex"), not a dash. '
              'The narrow rule turns it into a boundary, giving `noor s complex`, which is exactly what the v1 key gives for a real apostrophe; '
              'ftfy deletes it (`noors complex`), which would disagree with a counterpart that kept the apostrophe.']
    lines += ['', f'## Deterministic sample (includes some flagged rows): {len(sample):,} rows ({n_fields:,} fields)', '',
              f'ftfy changed **{n_changed:,}** fields. Characters it removed or replaced (top 12): '
              + ', '.join(f'`{c!r}` U+{ord(c):04X} x{n}' for c, n in changed.most_common(12)), '',
              'ftfy is a general normaliser (it also uncurls quotes, deletes some format characters and fixes widths). '
              'It is therefore NOT enabled in the pipeline: the narrow rule covers the only mojibake pattern present in the data, '
              'measured to have no effect on exact matching.']
    return '\n'.join(lines) + '\n', {'flagged_fields': len(fields), 'ftfy_equal_to_narrow_rule': equal, 'ftfy_differs': differ,
                                    'ftfy_unchanged': unchanged, 'sample_fields': n_fields, 'sample_fields_changed_by_ftfy': n_changed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--max-groups', type=int, default=0, help='limit row groups per file (smoke run; writes nothing)')
    args = parser.parse_args()

    audit = json.loads((ROOT / 'reports' / 'eda' / 'full_audit.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'manifests' / 'input_manifest_v1.json').read_text(encoding='utf-8'))
    work = tasks(args.max_groups)
    print(f'{len(work)} row-group tasks, {args.workers} workers', flush=True)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = []
        for i, result in enumerate(pool.map(scan.scan_row_group, work, chunksize=1), 1):
            results.append(result)
            if i % 40 == 0 or i == len(work):
                print(f'  {i}/{len(work)} row groups, {sum(r["rows"] for r in results):,} rows, {time.perf_counter() - started:.0f}s', flush=True)
    merged = scan.merge(results)
    wall = time.perf_counter() - started
    counts = merged['counts']
    metric_total = lambda m: sum(v for (t, c, k), v in counts.items() if k == m)

    rows_scanned = merged['rows']
    full = not args.max_groups
    checks = {}
    if full:
        checks['every_row_scanned'] = rows_scanned == manifest['totals']['source_rows']
        comparison = audit_comparison(counts, audit)
        checks['flags_equal_audit_sql_counts'] = all(r['equal'] for r in comparison)
    else:
        comparison = []
    checks['v1_parity_python_vs_duckdb_all_rows'] = metric_total('v1_parity_fail:name') + metric_total('v1_parity_fail:address') == 0
    empties = {m: metric_total(m) for m in sorted({k for (_t, _c, k) in counts if k.startswith('empty:') or k == 'addr_new_empty'})}
    checks['no_new_empty_views'] = all(v == 0 for v in empties.values())
    checks['no_marks_or_numbers_lost'] = metric_total('mn_lost:name_hyg') + metric_total('mn_lost:address_clean') == 0
    idem = {m: metric_total(m) for m in sorted({k for (_t, _c, k) in counts if k.startswith('not_idempotent:')})}
    checks['all_views_idempotent'] = all(v == 0 for v in idem.values())
    listed, missed = dotted_check(merged['dotted_census'], full)
    if full:
        checks['dotted_lexicon_counts_match_census'] = all(v['equal'] for v in listed.values())
        checks['no_frequent_dotted_form_missing_from_lexicon'] = not missed
    verification = {
        'rows_scanned': rows_scanned, 'wall_seconds': round(wall, 1), 'rows_per_second_wall': round(rows_scanned / wall),
        'cpu_seconds_in_workers': round(merged['seconds'], 1), 'us_per_row_cpu': round(1e6 * merged['seconds'] / max(rows_scanned, 1), 1),
        'peak_worker_memory_mb': merged['peak_memory_mb'], 'workers': args.workers,
        'v1_parity_failures': {'name': metric_total('v1_parity_fail:name'), 'address': metric_total('v1_parity_fail:address'),
                               'first_examples': [list(x) for x in merged['parity_failures'][:10]]},
        'empties': empties, 'mn_lost': {'name_hyg': metric_total('mn_lost:name_hyg'), 'address_clean': metric_total('mn_lost:address_clean')},
        'not_idempotent': idem, 'dotted_lexicon_vs_census': listed, 'frequent_dotted_forms_missing_from_lexicon': missed,
        'audit_sql_comparison_all_equal': all(r['equal'] for r in comparison) if comparison else None,
        'lexicon_sha256': {'legal_dotted.tsv': lexicon_sha256('legal_dotted.tsv')},
        'hygiene_version': __import__('cleaning').HYGIENE_VERSION, 'checks': checks, 'passed': all(checks.values()),
    }
    print(json.dumps({k: verification[k] for k in ['rows_scanned', 'wall_seconds', 'us_per_row_cpu', 'peak_worker_memory_mb', 'checks', 'passed']}, indent=2))
    print('v1 parity failures:', verification['v1_parity_failures']['name'], verification['v1_parity_failures']['address'])
    print('frequent dotted forms missing from lexicon:', missed)
    if not full:
        print('smoke run: nothing written')
        return 0 if verification['passed'] else 1

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'hygiene_change_counts.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['table', 'country', 'metric', 'count', 'rows', 'percent'])
        row_counts = {(t, c): v for (t, c, k), v in counts.items() if k == 'rows'}
        for (t, c, k), v in sorted(counts.items()):
            total = row_counts[(t, c)]
            writer.writerow([t, c, k, v, total, f'{100 * v / total:.4f}'])
    (OUT / 'hygiene_verification.json').write_text(json.dumps(verification, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    with (OUT / 'hygiene_examples.md').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('# Hygiene before/after examples\n\nFirst four rows (by entity ID) that each repair changed, over all six files. '
                     'The first string is the raw field, the second is `name_hyg` (a v1-style key) or `address_clean` (text view).\n')
        for (field, code), items in sorted(merged['examples'].items()):
            stream.write(f'\n## {field}: `{code}`\n\n')
            for eid, raw, cleaned in items:
                stream.write(f'- {eid}: `{raw!r}` -> `{cleaned!r}`\n')
    text, ftfy_summary = ftfy_experiment(merged['flagged'], merged['sample'])
    (OUT / 'ftfy_experiment.md').write_text(text, encoding='utf-8', newline='\n')
    verification['ftfy_experiment'] = ftfy_summary
    (OUT / 'hygiene_verification.json').write_text(json.dumps(verification, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    print('wrote', ', '.join(p.name for p in sorted(OUT.glob('*')) if p.name.startswith(('hygiene', 'ftfy'))))
    print('ftfy:', ftfy_summary)
    return 0 if verification['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
