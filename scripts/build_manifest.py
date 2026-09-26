"""Phase 1: build (or verify) the versioned input manifest.

    python scripts/build_manifest.py            # build manifests/input_manifest_v1.json + .sha256 + .run.json
    python scripts/build_manifest.py --check    # rebuild and fail if the recorded manifest is not reproduced byte for byte

The manifest is deterministic. Timings, memory and library versions are written to a separate run record so they never
change the manifest hash that later outputs record.
"""
import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from cleaning import manifest as m  # noqa: E402

OUT_DIR = ROOT / 'manifests'
MANIFEST = OUT_DIR / f'{m.MANIFEST_VERSION}.json'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='rebuild and compare with the recorded manifest')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--memory', default='4GB', help='DuckDB memory limit')
    parser.add_argument('--threads', type=int, default=4, help='DuckDB threads')
    args = parser.parse_args()

    manifest, run = m.build_manifest(ROOT, workers=args.workers, duckdb_memory=args.memory,
                                     duckdb_threads=args.threads, log=lambda text: print(text, flush=True))
    text = m.dumps(manifest)

    if args.check:
        if not MANIFEST.exists():
            print(f'no recorded manifest at {MANIFEST}', file=sys.stderr)
            return 2
        recorded = MANIFEST.read_text(encoding='utf-8')
        if recorded != text:
            print('MISMATCH: the rebuilt manifest differs from the recorded one', file=sys.stderr)
            return 1
        print(f'OK: rebuilt manifest is byte-identical to {MANIFEST.relative_to(ROOT).as_posix()} '
              f'(sha256 {m.sha256_file(MANIFEST)})')
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(text, encoding='utf-8', newline='\n')
    digest = m.sha256_file(MANIFEST)
    (OUT_DIR / f'{m.MANIFEST_VERSION}.sha256').write_text(f'{digest}  {MANIFEST.name}\n', encoding='utf-8', newline='\n')
    import duckdb, psutil, pyarrow
    run.update({'created_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                'platform': platform.platform(), 'cpu_count': psutil.cpu_count(),
                'duckdb': duckdb.__version__, 'pyarrow': pyarrow.__version__, 'manifest_sha256': digest})
    (OUT_DIR / f'{m.MANIFEST_VERSION}.run.json').write_text(json.dumps(run, indent=2, sort_keys=True) + '\n',
                                                          encoding='utf-8', newline='\n')
    print(f'wrote {MANIFEST.relative_to(ROOT).as_posix()}  sha256 {digest}')
    print(json.dumps({'totals': manifest['totals'], 'reconciliation': manifest['reconciliation']}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
