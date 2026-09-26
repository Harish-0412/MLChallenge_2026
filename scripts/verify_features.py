"""Phase 6: verify a built feature table (see src/cleaning/feature_verify.py for the list of checks).

    python scripts/verify_features.py --version feat_v2_0_sample       # sample build: skips the comparison with the full-scan reports
    python scripts/verify_features.py --version feat_v2_0              # full build: everything, including the scan cross-checks

Writes reports/cleaning/feature_verification_<version>.json and exits non-zero if any check fails.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from cleaning import feature_verify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', required=True)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--no-determinism', action='store_true', help='skip the scratch rebuilds (G)')
    args = parser.parse_args()
    started = time.perf_counter()
    report = feature_verify.run_verification(ROOT, args.version, determinism=not args.no_determinism, threads=args.threads)
    out = report.to_json()
    out.update({'version': args.version, 'seconds': round(time.perf_counter() - started, 1)})
    path = ROOT / 'reports' / 'cleaning' / f'feature_verification_{args.version}.json'
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f"\n{out['passed']}/{out['passed'] + out['failed']} checks passed in {out['seconds']}s -> {path.relative_to(ROOT)}")
    for c in report.failed:
        print('FAILED:', c['name'], '|', c['detail'])
    return 1 if report.failed else 0


if __name__ == '__main__':
    sys.exit(main())
