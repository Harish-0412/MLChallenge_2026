"""Phase 5 evidence (unlabeled): what the address fields actually contain, per country and source.

    python scripts/address_token_census.py

Outputs (reports/cleaning/address_census/):
  segments.csv        most frequent comma-separated SEGMENTS per country/source (states, regions, cities, placeholders)
  tokens.csv          token counts and S2/S3-vs-S1 lift per country (abbreviation candidates)
  abbreviation_candidates.md   token pairs (abbreviation -> expansion) proposed by prefix/subsequence and lift, for manual review
  summary.json        prevalence of placeholder segments, postal-like tokens, non-Latin segments, segment counts
Labels are never read. Tokens come from the v1 keys (letters/marks/numbers), segments from the raw text.
"""
import csv
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / 'data' / 'interim'
OUT = ROOT / 'reports' / 'cleaning' / 'address_census'
TABLES = [(s, sp) for sp in ('train', 'test') for s in (1, 2, 3)]


def rel(source, split):
    return f"read_parquet('{(INTERIM / f'{split}_source{source}.parquet').as_posix()}')"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=3')

    # ------------------------------------------------------------ segments
    parts = []
    for source, split in TABLES:
        parts.append(f"""SELECT 'S{source}' AS source, '{split}' AS split, country, trim(unnest(string_split(business_address, ','))) AS segment
                         FROM {rel(source, split)} WHERE business_address <> ''""")
    con.execute('CREATE TABLE seg AS ' + ' UNION ALL '.join(parts))
    con.execute(f"""COPY (SELECT source, split, country, segment, count(*) AS n FROM seg GROUP BY ALL HAVING count(*) >= 2000
                    ORDER BY country, source, n DESC) TO '{(OUT / 'segments.csv').as_posix()}' (HEADER, DELIMITER ',')""")

    # ------------------------------------------------------------ tokens and lift
    parts = []
    for source, split in TABLES:
        parts.append(f"""SELECT 'S{source}' AS source, country, unnest(string_split(address_key, ' ')) AS token FROM {rel(source, split)} WHERE address_key <> ''""")
    con.execute('CREATE TABLE tok AS ' + ' UNION ALL '.join(parts))
    con.execute("""CREATE TABLE tok_counts AS SELECT country, token,
        sum(CASE WHEN source='S1' THEN 1 ELSE 0 END) AS s1, sum(CASE WHEN source<>'S1' THEN 1 ELSE 0 END) AS s23 FROM tok GROUP BY ALL HAVING count(*) >= 3000""")
    totals = dict(con.execute("SELECT country || '|' || CASE WHEN source='S1' THEN 'S1' ELSE 'S23' END, count(*) FROM tok GROUP BY ALL").fetchall())
    rows = con.execute('SELECT country, token, s1, s23 FROM tok_counts ORDER BY country, s1 + s23 DESC').fetchall()
    out_rows = []
    for country, token, s1, s23 in rows:
        t1, t23 = totals.get(f'{country}|S1', 1), totals.get(f'{country}|S23', 1)
        share1, share23 = s1 / t1, s23 / t23
        out_rows.append({'country': country, 'token': token, 's1': s1, 's23': s23, 's1_share': f'{share1:.6f}', 's23_share': f'{share23:.6f}',
                         'lift': f'{share23 / max(share1, 1e-9):.2f}'})
    with (OUT / 'tokens.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)

    # abbreviation candidates: a token with lift >= 4 (or absent in S1) that is a proper prefix or subsequence of a frequent S1 token
    lines = ['# Abbreviation candidates (unlabeled)', '',
             'Token `abbr` is >= 4x more frequent (per token) in S2/S3 than in S1 and is a prefix or an in-order subsequence of a frequent S1 token `full` starting with the same letter. '
             'Reviewed by hand before entering `address_abbrev.tsv`.', '']
    def subsequence(a, b):
        it = iter(b)
        return all(ch in it for ch in a)
    for country in sorted({r['country'] for r in out_rows}):
        rs = [r for r in out_rows if r['country'] == country]
        frequent_full = [r for r in rs if int(r['s1']) >= 3000 and r['token'].isalpha() and r['token'].isascii() and len(r['token']) >= 4]
        lines += [f'## {country}', '', '| abbr | S1 | S2+S3 | lift | expansion candidates (by S1 count) |', '|---|---:|---:|---:|---|']
        cands = []
        for r in rs:
            t = r['token']
            if not (t.isalpha() and t.isascii() and 2 <= len(t) <= 5) or float(r['lift']) < 4 or int(r['s23']) < 3000:
                continue
            fulls = sorted((f for f in frequent_full if f['token'] != t and f['token'][0] == t[0] and len(f['token']) > len(t) and subsequence(t, f['token'])),
                           key=lambda f: -int(f['s1']))[:4]
            if fulls:
                cands.append((t, r, fulls))
        for t, r, fulls in sorted(cands, key=lambda c: -int(c[1]['s23']))[:60]:
            lines.append(f"| `{t}` | {int(r['s1']):,} | {int(r['s23']):,} | {r['lift']} | " + ', '.join(f"`{f['token']}` ({int(f['s1']):,})" for f in fulls) + ' |')
        lines.append('')
    (OUT / 'abbreviation_candidates.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')

    # ------------------------------------------------------------ summary prevalences
    summary = {}
    for source, split in TABLES:
        r = rel(source, split)
        row = con.execute(f"""SELECT country, count(*) AS rows, count_if(business_address <> '') AS nonempty,
            count_if(regexp_matches(business_address, '(?i)(^|,)\\s*(null|n/a|na|none|nan)\\s*(,|$)')) AS placeholder_segment_rows,
            count_if(regexp_matches(business_address, '(?i)(^|[^a-z0-9])null([^a-z0-9]|$)')) AS null_word_rows,
            count_if(regexp_matches(business_address, '(^|[^0-9])[0-9]{{5}}([^0-9]|$)')) AS five_digit_rows,
            count_if(regexp_matches(business_address, '(^|[^0-9])[0-9]{{6}}([^0-9]|$)')) AS six_digit_rows,
            count_if(regexp_matches(business_address, '(^|[^0-9])0[0-9]+')) AS leading_zero_rows,
            count_if(regexp_matches(business_address, '[^\\x{{0000}}-\\x{{024F}}]')) AS non_latin_rows,
            avg(len(string_split(business_address, ',')))::DOUBLE AS avg_segments
            FROM {r} GROUP BY country ORDER BY country""").fetchall()
        summary[f'{split}_source{source}'] = [dict(zip(['country', 'rows', 'nonempty', 'placeholder_segment_rows', 'null_word_rows', 'five_digit_rows', 'six_digit_rows',
                                                           'leading_zero_rows', 'non_latin_rows', 'avg_segments'], x)) for x in row]
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print('wrote', ', '.join(p.name for p in sorted(OUT.iterdir())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
