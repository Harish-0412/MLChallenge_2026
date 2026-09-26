"""Phase 0 baseline check: recompute input SHA-256 values, compare with the audit, and write a text list for Member B.

Run from the project root:  python scripts/check_baseline.py
Exit code 0 only if every recomputed hash and byte size equals the value stored in reports/eda/full_audit.json.
The output file is plain text so it can be exchanged and diffed without sharing multi-gigabyte files.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'reports' / 'eda' / 'full_audit.json'
OUT = ROOT / 'reports' / 'cleaning' / 'baseline_hashes.txt'


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding='utf-8'))
    if not audit.get('complete'):
        print('full_audit.json is not marked complete', file=sys.stderr)
        return 2
    lines = ['# sha256  bytes  path (relative to project root); recomputed by scripts/check_baseline.py']
    failures = 0
    for item in sorted(audit['files'], key=lambda x: x['file']):
        path = ROOT / item['file']
        digest, size = sha256(path), path.stat().st_size
        ok = digest == item['sha256'] and size == item['bytes']
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {item['file']}  {size:,} bytes  {digest[:16]}...")
        lines.append(f"{digest}  {size}  {Path(item['file']).as_posix()}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(audit["files"])} files checked, {failures} mismatches. Wrote {OUT.relative_to(ROOT).as_posix()}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
