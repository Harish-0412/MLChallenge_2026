"""Phase 3 evidence: first/last token frequencies and Source-1 document frequencies, per country, from the v1 keys.

    python scripts/name_token_census.py

Outputs (reports/cleaning/name_token_census/):
  first_last_tokens.csv   source, split, country, position (first|last), token, count, rows   (count >= 200)
  s1_document_freq.csv    split, country, token, docs, rows, share   (Source 1 only; share >= 0.05%; train and test kept apart)
  top_tokens.md           human-readable top lists used to curate the legal-form lexicon

Unlabeled statistics only: labels are never read. v1 keys split dotted acronyms (L.L.C. -> l l c), which is why
single-letter tokens are ignored when reading the lists; the dotted lexicon handles those forms.
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / 'data' / 'interim'
OUT = ROOT / 'reports' / 'cleaning' / 'name_token_census'
TABLES = [(s, sp) for sp in ('train', 'test') for s in (1, 2, 3)]
MIN_COUNT = 200


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')
    parts = []
    for source, split in TABLES:
        path = (INTERIM / f'{split}_source{source}.parquet').as_posix()
        for position, expr in (('first', "list_extract(string_split(name_key, ' '), 1)"),
                               ('last', "list_extract(string_split(name_key, ' '), -1)")):
            parts.append(f"""SELECT 'S{source}' AS source, '{split}' AS split, country, '{position}' AS position, {expr} AS token, count(*) AS count,
                (SELECT count(*) FROM read_parquet('{path}') r WHERE r.country=t.country) AS rows
                FROM read_parquet('{path}') t GROUP BY country, token HAVING count(*) >= {MIN_COUNT}""")
    con.execute('CREATE TABLE first_last AS ' + ' UNION ALL '.join(parts))
    con.execute(f"COPY (SELECT * FROM first_last ORDER BY source, split, country, position, count DESC, token) TO '{(OUT / 'first_last_tokens.csv').as_posix()}' (HEADER, DELIMITER ',')")

    s1 = ' UNION ALL '.join(f"SELECT '{sp}' AS split, entity_id, country, name_key FROM read_parquet('{(INTERIM / f'{sp}_source1.parquet').as_posix()}')" for sp in ('train', 'test'))
    con.execute(f"""CREATE TABLE df AS
        SELECT split, country, tok AS token, count(*) AS docs FROM (SELECT split, country, unnest(list_distinct(string_split(name_key, ' '))) AS tok FROM ({s1}))
        GROUP BY split, country, tok""")
    con.execute("CREATE TABLE s1_rows AS SELECT split, country, count(*) AS rows FROM (" + s1 + ") GROUP BY split, country")
    con.execute(f"""COPY (SELECT d.split, d.country, d.token, d.docs, r.rows, d.docs*1.0/r.rows AS share FROM df d JOIN s1_rows r USING (split, country)
        WHERE d.docs*1.0/r.rows >= 0.0005 ORDER BY d.split, d.country, d.docs DESC) TO '{(OUT / 's1_document_freq.csv').as_posix()}' (HEADER, DELIMITER ',')""")

    lines = ['# Token census (v1 keys, unlabeled)', '',
             'Top first and last tokens per country and source. Legal-form candidates are curated from these lists; '
             'single-letter tokens come from dotted acronyms and are handled by `legal_dotted.tsv`.', '']
    for country in [r[0] for r in con.execute('SELECT DISTINCT country FROM first_last ORDER BY 1').fetchall()]:
        lines += [f'## {country}', '']
        for position in ('last', 'first'):
            lines += [f'### most frequent {position} tokens', '', '| token | S1 | S2 | S3 |', '|---|---:|---:|---:|']
            rows = con.execute(f"""SELECT token,
                sum(CASE WHEN source='S1' THEN count ELSE 0 END), sum(CASE WHEN source='S2' THEN count ELSE 0 END), sum(CASE WHEN source='S3' THEN count ELSE 0 END)
                FROM first_last WHERE country=? AND position=? AND length(token)>1 GROUP BY token ORDER BY sum(count) DESC LIMIT 45""", [country, position]).fetchall()
            lines += [f'| `{t}` | {a:,} | {b:,} | {c:,} |' for t, a, b, c in rows]
            lines.append('')
    (OUT / 'top_tokens.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print('wrote', ', '.join(p.name for p in sorted(OUT.iterdir())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
