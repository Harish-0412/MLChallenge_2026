"""Phase 6: build the per-record feature table.

    python scripts/build_features.py --version feat_v2_0_sample --max-groups 1          # small sample build (first row group of each table)
    python scripts/build_features.py --version feat_v2_0 --workers 6                    # full build (24,229,173 rows)

Output: data/features/<version>/split=*/source=*/country=*/part-*.parquet (+ _manifest.json, _run.json).
Refuses to overwrite an existing version and checks the inputs against manifests/input_manifest_v1.json first.
Read it back with:  duckdb.read_parquet('data/features/<version>/**/*.parquet', hive_partitioning=true)
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import FEATURE_VERSION  # noqa: E402
from cleaning import pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default=FEATURE_VERSION, help=f'output version name (default {FEATURE_VERSION})')
    parser.add_argument('--workers', type=int, default=6, help='worker processes (12 cores / 16 GB machine: 6 leaves headroom)')
    parser.add_argument('--max-groups', type=int, default=0, help='sample build: only the first N row groups of each input table (0 = all)')
    parser.add_argument('--flush-rows', type=int, default=pipeline.FLUSH_ROWS, help='rows buffered per country before writing')
    args = parser.parse_args()
    if not args.max_groups and args.version != FEATURE_VERSION:
        print(f'note: full build under a non-default version name {args.version!r} (code version is {FEATURE_VERSION!r})')
    if args.max_groups and args.version == FEATURE_VERSION:
        print(f'refusing: a sample build must not use the release version name {FEATURE_VERSION!r}', file=sys.stderr)
        return 2
    result = pipeline.build(ROOT, args.version, workers=args.workers, max_groups=args.max_groups, flush_rows=args.flush_rows, command=sys.argv)
    totals, run = result['manifest']['totals'], result['run']
    print(json.dumps({'version': args.version, 'rows': totals['rows'], 'files': totals['files'], 'bytes': totals['bytes'],
                      'wall_seconds': run['wall_seconds'], 'rows_per_second': run['rows_per_second_wall'],
                      'peak_worker_memory_mb': run['peak_worker_memory_mb']}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
