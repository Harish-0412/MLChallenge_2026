"""Phase 4 evidence: the most frequent trailing/leading tokens of native-script names, per Indic script (unlabeled).

    python scripts/native_legal_census.py

Uses TRAIN S2+S3 India names that contain the script; tokenisation matches the hygiene layer (ZWNJ/ZWJ deleted first, then the
v1 letters/marks/numbers rule). Each frequent token is transliterated with anyascii and compared, by phonetic skeleton, with the
Latin legal words. Output: reports/cleaning/native_legal_candidates.md and native_legal_candidates.csv, reviewed by hand before
anything is written to the lexicon (scripts/build_name_lexicons.py, CURATED_NATIVE). Labels are never read.
"""
import csv
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cleaning import translit as T  # noqa: E402
from cleaning.lexicons import legal_index  # noqa: E402

INTERIM = ROOT / 'data' / 'interim'
OUT = ROOT / 'reports' / 'cleaning'
TOP = 30
KEY = r"trim(regexp_replace(lower(nfc_normalize(replace(replace(business_name, chr(8204), ''), chr(8205), ''))), '[^\p{L}\p{M}\p{N}]+', ' ', 'g'))"


def main() -> int:
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')
    latin_legal = {t: c for t, (c, _r) in legal_index('India').items()}
    latin_sk = {}
    for token in latin_legal:
        for coarse in (False, True):
            latin_sk.setdefault(T.skeleton(token, coarse), set()).add(token)
    rel = ' UNION ALL '.join(f"SELECT business_name FROM read_parquet('{(INTERIM / f'train_source{s}.parquet').as_posix()}') WHERE country='India'" for s in (2, 3))
    lines = ['# Native-script legal-word candidates (unlabeled, train S2+S3 India)', '',
             'For each script: the most frequent last tokens of names that contain the script. `sk` is the coarse phonetic skeleton of the '
             'anyascii transliteration; `auto` lists Latin legal words with the same skeleton. `share` is the share of that script\'s names.', '']
    rows_out = []
    for script in T.INDIC_SCRIPTS:
        con.execute(f"CREATE OR REPLACE TEMP TABLE names AS SELECT {KEY} AS k FROM ({rel}) WHERE regexp_matches(business_name, '\\p{{{script}}}')")
        total = con.execute('SELECT count(*) FROM names').fetchone()[0]
        lines += [f'## {script} ({total:,} names)', '', '| token | translit | sk | last | last % | 2nd-last | 2nd-last % | first | auto |', '|---|---|---|---:|---:|---:|---:|---:|---|']
        rows = con.execute(f"""SELECT tok, sum(last_n) AS last_n, sum(second_n) AS second_n, sum(first_n) AS first_n FROM (
              SELECT list_extract(string_split(k,' '), -1) AS tok, count(*) AS last_n, 0 AS second_n, 0 AS first_n FROM names GROUP BY 1
              UNION ALL SELECT list_extract(string_split(k,' '), -2), 0, count(*), 0 FROM names WHERE len(string_split(k,' '))>1 GROUP BY 1
              UNION ALL SELECT list_extract(string_split(k,' '), 1), 0, 0, count(*) FROM names GROUP BY 1)
              GROUP BY tok ORDER BY sum(last_n) + sum(second_n) DESC LIMIT {TOP}""").fetchall()
        for token, last_n, second_n, first_n in rows:
            ascii_text = T.to_ascii(token)
            sk = T.skeleton(ascii_text, True)
            auto = sorted(latin_sk.get(sk, ()))
            lines.append(f'| `{token}` | {ascii_text} | {sk} | {last_n:,} | {100 * last_n / total:.1f}% | {second_n:,} | {100 * second_n / total:.1f}% | {first_n:,} | {", ".join(auto)} |')
            rows_out.append({'script': script, 'token': token, 'translit': ascii_text, 'skeleton_coarse': sk, 'last': last_n, 'second_last': second_n,
                             'first': first_n, 'names_in_script': total, 'auto_latin_match': ' '.join(auto)})
        lines.append('')
    (OUT / 'native_legal_candidates.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    with (OUT / 'native_legal_candidates.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)
    print('wrote native_legal_candidates.md / .csv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
