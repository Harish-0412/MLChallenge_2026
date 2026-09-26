"""Phase 5 acceptance: extraction-quality sample from a BUILT feature table (30 rows per country x source, deterministic).

    python scripts/address_extraction_sample.py --version feat_v2_0

Rows are ordered by hash(entity_id) (no random seed), so the sample is reproducible and independent of build order. Output:
reports/cleaning/address_extraction_sample.md - the raw address and every extracted piece side by side, for hand review.
"""
import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PER_GROUP = 30


def cell(value) -> str:
    text = ' ; '.join(value) if isinstance(value, list) else str(value)
    return text.replace('|', '\\|').replace('\n', ' ') or '-'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='feat_v2_0')
    parser.add_argument('--per-group', type=int, default=PER_GROUP)
    args = parser.parse_args()
    glob = (ROOT / 'data' / 'features' / args.version / 'split=*' / 'source=*' / '*' / '*.parquet').as_posix()
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT country, source, split, entity_id, business_address, address_clean, address_segments, address_canon, address_state_canon, address_state_conf,
               address_numbers_raw, address_numbers_canon, address_number_ctx, address_postal_candidates, address_city_candidates, address_extras,
               address_null_tokens, address_parse_conf
        FROM (SELECT *, row_number() OVER (PARTITION BY country, source ORDER BY hash(entity_id)) AS rn
              FROM read_parquet('{glob}', hive_partitioning=false) WHERE NOT address_missing)
        WHERE rn <= {args.per_group} ORDER BY country, source, rn""").fetchall()
    out = [f'# Address extraction sample ({args.version})', '',
           f'{args.per_group} non-missing addresses per country x source, ordered by hash(entity_id) (deterministic). For hand review: the raw address, the canonical '
           'segments, state (confidence), number spans (raw -> canon | context), postal candidates, city candidates, removed injected components and the parse '
           'confidence. Review notes are at the end of the file.', '']
    group = None
    for (country, source, split, eid, raw, clean, segments, canon, state, conf, nraw, ncanon, nctx, postal, cities, extras, nulls, parse) in rows:
        if (country, source) != group:
            group = (country, source)
            out += [f'## {country} - source {source}', '', '| id | raw address | canonical segments | state (conf) | numbers raw -> canon (ctx) | postal | city candidates | removed / nulls | parse |', '|---|---|---|---|---|---|---|---|---|']
        numbers = ' ; '.join(f'{a} -> {b}' + (f' ({c})' if c else '') for a, b, c in zip(nraw, ncanon, nctx))
        out.append(f'| {eid} ({split}) | {cell(raw)} | {cell(segments)} | {cell(state)} ({conf}) | {cell(numbers)} | {cell(postal)} | {cell(cities)} | '
                   f"{cell(extras)}{' / nulls ' + str(nulls) if nulls else ''} | {parse} |")
    text = '\n'.join(out) + '\n'
    path = ROOT / 'reports' / 'cleaning' / 'address_extraction_sample.md'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    notes = existing.split('\n## Review notes', 1)
    if len(notes) == 2:
        text += '\n## Review notes' + notes[1]
    path.write_text(text, encoding='utf-8', newline='\n')
    print(f'{len(rows)} rows -> {path.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
