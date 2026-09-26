"""Full-dataset read-only audit; writes derived DB, Parquet, JSON and CSV reports.

Run from the project root: python scripts/audit_dataset.py
Original challenge files are never edited. A fresh run refuses an existing DB;
--resume reuses only tables whose stored input SHA-256 matches the current file.
"""
import argparse
import csv
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import rapidfuzz
from rapidfuzz.fuzz import ratio, token_set_ratio

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COLUMNS = ["entity_id", "business_name", "business_address", "country"]
TRUTH_COLUMNS = ["source1_entity_id", "matched_entity_ids"]
VERSION = "nfc_lower_lmn_v1"


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def records(connection, sql):
    cursor = connection.execute(sql)
    names = [x[0] for x in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def dump_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def dump_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def csv_scan(path, columns):
    schema = "{" + ",".join(f"{literal(k)}:'VARCHAR'" for k in columns) + "}"
    return f"""read_csv({literal(path.as_posix())}, delim='\t', header=true,
        columns={schema}, auto_detect=false, quote='"', escape='"',
        force_not_null=[{','.join(literal(k) for k in columns)}],
        strict_mode=true, ignore_errors=false, null_padding=false)"""


def key_sql(column):
    return rf"trim(regexp_replace(lower(nfc_normalize({column})), '[^\p{{L}}\p{{M}}\p{{N}}]+', ' ', 'g'))"


def profile(connection, table):
    return records(connection, rf"""
        SELECT country, count(*) AS rows,
        count(*) - count(DISTINCT entity_id) AS duplicate_id_rows,
        count_if(NOT regexp_full_match(entity_id, 'S[123]-[0-9]+')) AS malformed_ids,
        count_if(NOT starts_with(entity_id, 'S{table[-1]}-')) AS wrong_prefix,
        count_if(trim(business_name)='') AS missing_name,
        count_if(trim(business_address)='') AS missing_address,
        count_if(trim(country)='') AS missing_country,
        count_if(business_name <> trim(business_name)) AS name_edge_whitespace,
        count_if(business_address <> trim(business_address)) AS address_edge_whitespace,
        count_if(regexp_matches(business_name, '\s{{2,}}')) AS name_repeated_whitespace,
        count_if(regexp_matches(business_address, '\s{{2,}}')) AS address_repeated_whitespace,
        count_if(regexp_matches(business_name, '[^\x00-\x7F]')) AS non_ascii_name,
        count_if(regexp_matches(business_address, '[^\x00-\x7F]')) AS non_ascii_address,
        count_if(regexp_matches(business_name, '[\x{{0900}}-\x{{097F}}]')) AS devanagari_name,
        count_if(regexp_matches(business_name, '\p{{M}}')) AS name_contains_combining_marks,
        count_if(regexp_matches(business_address, '\p{{M}}')) AS address_contains_combining_marks,
        count_if(contains(business_name, chr(65533)) OR contains(business_address, chr(65533))) AS replacement_character_rows,
        count_if(regexp_matches(business_name || business_address, '\p{{Cc}}')) AS control_character_rows,
        count_if(regexp_matches(business_name || business_address, '\p{{Cf}}')) AS format_character_rows,
        count_if(lower(trim(business_name)) IN ('na','n/a','null','none','nan','unknown','-')) AS name_placeholder_like,
        count_if(lower(trim(business_address)) IN ('na','n/a','null','none','nan','unknown','-')) AS address_placeholder_like,
        count_if(name_key='') AS empty_name_key,
        count_if(address_key='') AS empty_address_key,
        count_if(NOT regexp_matches(business_address, '[0-9]')) AS address_without_ascii_digit,
        quantile_disc(length(business_name), [0.5,0.95,0.99]) AS name_length_p50_p95_p99,
        max(length(business_name)) AS name_max_length,
        quantile_disc(length(business_address), [0.5,0.95,0.99]) AS address_length_p50_p95_p99,
        max(length(business_address)) AS address_max_length
        FROM {table} GROUP BY country ORDER BY country
    """)


def collisions(connection, table, keys):
    grouping = ','.join(keys)
    return records(connection, f"""
        SELECT country, count(*) AS key_groups, count_if(n>1) AS repeated_key_groups,
        sum(n-1) AS repeat_rows_after_first, max(n) AS largest_group
        FROM (SELECT country, {grouping}, count(*) n FROM {table}
              WHERE name_key <> '' GROUP BY country, {grouping})
        GROUP BY country ORDER BY country
    """)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--memory', default='2GB')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    started = time.time()
    output = ROOT / 'reports' / 'eda'
    derived = ROOT / 'data' / 'interim'
    output.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    database = derived / 'audit.duckdb'
    if database.exists() and not args.resume:
        raise SystemExit('Derived database exists. Use --resume; raw data is never changed.')
    con = duckdb.connect(str(database))
    con.execute(f"SET memory_limit={literal(args.memory)}")
    con.execute(f'SET threads={args.threads}')
    con.execute('SET preserve_insertion_order=false')
    con.execute(f"SET temp_directory={literal((derived/'spill').as_posix())}")
    con.execute('CREATE TABLE IF NOT EXISTS input_manifest (name VARCHAR PRIMARY KEY, sha256 VARCHAR, normalization_version VARCHAR)')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
              'duckdb': duckdb.__version__, 'rapidfuzz': rapidfuzz.__version__,
              'normalization_version': VERSION, 'scope': 'All six source TSVs and all ground-truth rows',
              'files': [], 'profiles': {}, 'collisions': {}, 'cross_split': [], 'positive_pairs': [],
              'pair_sample': {}, 'negative_sample_warning': 'No hard-negative or retrieval experiment is included in this audit.'}
    for split in ['train', 'test']:
        for source in [1, 2, 3]:
            table = f'{split}_source{source}'
            path = ROOT/'student_resource'/'dataset'/split/f'{table}.tsv'
            print(f'IMPORT/PROFILE {table}', flush=True)
            digest = sha256(path)
            report['files'].append({'file': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': digest})
            old = con.execute('SELECT sha256,normalization_version FROM input_manifest WHERE name=?', [table]).fetchone()
            if old and old != (digest, VERSION):
                raise ValueError(f'Input or normalization changed for {table}; use a new derived database.')
            if not old:
                with path.open(encoding='utf-8-sig') as stream:
                    if stream.readline().rstrip('\r\n').split('\t') != SOURCE_COLUMNS:
                        raise ValueError(f'Wrong header: {path}')
                con.execute('BEGIN')
                con.execute(f'''CREATE TABLE {table} AS SELECT *,
                    {key_sql('business_name')} AS name_key,
                    {key_sql('business_address')} AS address_key
                    FROM {csv_scan(path, SOURCE_COLUMNS)}''')
                con.execute('INSERT INTO input_manifest VALUES (?,?,?)', [table, digest, VERSION])
                con.execute('COMMIT')
            report['profiles'][table] = profile(con, table)
            report['collisions'][table] = {
                'name': collisions(con, table, ['name_key']),
                'name_and_address': collisions(con, table, ['name_key', 'address_key']),
                'duplicate_ids_global': con.execute(f'SELECT count(*)-count(DISTINCT entity_id) FROM {table}').fetchone()[0],
                'raw_payload_duplicate_rows': con.execute(f'SELECT count(*)-count(DISTINCT (business_name,business_address,country)) FROM {table}').fetchone()[0]}
            dump_json(output/'full_audit.json', report)
            parquet = derived/f'{table}.parquet'
            if not parquet.exists():
                con.execute(f"COPY {table} TO {literal(parquet.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)")
            print(f'DONE {table}: {sum(row["rows"] for row in report["profiles"][table]):,} rows', flush=True)
    print('CROSS-SPLIT CHECKS', flush=True)
    for source in [1, 2, 3]:
        report['cross_split'].append({
            'source': source,
            'same_id_overlap': con.execute(f'SELECT count(*) FROM test_source{source} t SEMI JOIN train_source{source} r USING(entity_id)').fetchone()[0],
            'test_records_with_exact_train_payload': con.execute(f'''SELECT count(*) FROM test_source{source} t SEMI JOIN train_source{source} r
                ON t.country=r.country AND t.business_name=r.business_name AND t.business_address=r.business_address''').fetchone()[0],
            'test_records_with_equal_normalized_train_payload': con.execute(f'''SELECT count(*) FROM test_source{source} t SEMI JOIN train_source{source} r
                ON t.country=r.country AND t.name_key=r.name_key AND t.address_key=r.address_key''').fetchone()[0]})
    print('LABEL INTEGRITY AND POSITIVE PAIRS', flush=True)
    path = ROOT/'student_resource'/'dataset'/'train'/'train_ground_truth.tsv'
    digest = sha256(path)
    report['files'].append({'file': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': digest})
    with path.open(encoding='utf-8-sig') as stream:
        if stream.readline().rstrip('\r\n').split('\t') != TRUTH_COLUMNS:
            raise ValueError('Wrong ground truth header')
    con.execute(f'CREATE OR REPLACE TABLE truth_rows AS SELECT * FROM {csv_scan(path, TRUTH_COLUMNS)}')
    con.execute("""CREATE OR REPLACE TABLE truth_pairs AS SELECT source1_entity_id,
        unnest(string_split(matched_entity_ids, ',')) AS target_id
        FROM truth_rows WHERE matched_entity_ids<>''""")
    report['truth_integrity'] = {
        'rows': con.execute('SELECT count(*) FROM truth_rows').fetchone()[0],
        'duplicate_s1_rows': con.execute('SELECT count(*)-count(DISTINCT source1_entity_id) FROM truth_rows').fetchone()[0],
        'missing_s1_rows': con.execute('SELECT count(*) FROM train_source1 s ANTI JOIN truth_rows g ON s.entity_id=g.source1_entity_id').fetchone()[0],
        'unknown_s1_rows': con.execute('SELECT count(*) FROM truth_rows g ANTI JOIN train_source1 s ON s.entity_id=g.source1_entity_id').fetchone()[0],
        'positive_links': con.execute('SELECT count(*) FROM truth_pairs').fetchone()[0],
        'duplicate_pairs': con.execute('SELECT count(*)-count(DISTINCT (source1_entity_id,target_id)) FROM truth_pairs').fetchone()[0],
        'targets_with_multiple_s1_owners': con.execute('SELECT count(*) FROM (SELECT target_id FROM truth_pairs GROUP BY target_id HAVING count(DISTINCT source1_entity_id)>1)').fetchone()[0],
        'wrong_target_prefix': con.execute("SELECT count(*) FROM truth_pairs WHERE NOT regexp_full_match(target_id,'S[23]-[0-9]+')").fetchone()[0]}
    report['match_counts'] = records(con, """SELECT s.country,
        CASE WHEN g.matched_entity_ids='' THEN 0 ELSE len(string_split(g.matched_entity_ids,',')) END AS matches,
        count(*) AS entities FROM truth_rows g JOIN train_source1 s ON g.source1_entity_id=s.entity_id
        GROUP BY s.country,matches ORDER BY s.country,matches""")
    report['ambiguous_s1_examples'] = records(con, '''SELECT country,name_key,address_key,count(*) AS s1_records
        FROM train_source1 GROUP BY country,name_key,address_key HAVING count(*)>1
        ORDER BY s1_records DESC,country,name_key,address_key LIMIT 12''')
    for source in [2, 3]:
        print(f'POSITIVE PAIR AUDIT S1-S{source}', flush=True)
        con.execute(f'''CREATE OR REPLACE TEMP TABLE pair_features AS SELECT
            g.source1_entity_id, g.target_id, a.country,
            b.entity_id IS NULL AS missing_target,
            a.country<>b.country AS country_mismatch,
            a.business_name=b.business_name AS raw_name_equal,
            a.name_key=b.name_key AS name_key_equal,
            a.business_address=b.business_address AND b.address_key<>'' AS raw_address_equal,
            a.address_key=b.address_key AND b.address_key<>'' AS address_key_equal,
            b.address_key='' AS target_address_missing,
            regexp_matches(b.business_name, '[\\x{{0900}}-\\x{{097F}}]') AS target_devanagari_name,
            regexp_matches(b.business_name || b.business_address, '\\p{{M}}') AS target_combining_marks,
            len(list_intersect(regexp_extract_all(a.address_key,'[0-9]+'),regexp_extract_all(b.address_key,'[0-9]+')))>0 AS shared_numeric_token,
            regexp_matches(a.address_key,'[0-9]') AND regexp_matches(b.address_key,'[0-9]') AS both_have_numeric_token
            FROM truth_pairs g JOIN train_source1 a ON g.source1_entity_id=a.entity_id
            LEFT JOIN train_source{source} b ON g.target_id=b.entity_id
            WHERE starts_with(g.target_id,'S{source}-')''')
        report['positive_pairs'] += records(con, f'''SELECT {source} AS target_source,country,count(*) AS links,
            count_if(missing_target) AS missing_targets, count_if(country_mismatch) AS country_mismatches,
            count_if(raw_name_equal) AS raw_name_equal, count_if(name_key_equal) AS name_key_equal,
            count_if(raw_address_equal) AS raw_address_equal, count_if(address_key_equal) AS address_key_equal,
            count_if(name_key_equal OR address_key_equal) AS exact_name_or_address_retrievable,
            count_if(target_address_missing) AS missing_target_addresses,
            count_if(target_devanagari_name) AS devanagari_target_names,
            count_if(target_combining_marks) AS target_contains_combining_marks,
            count_if(both_have_numeric_token) AS both_have_numeric_token,
            count_if(both_have_numeric_token AND NOT shared_numeric_token) AS disjoint_numeric_tokens
            FROM pair_features GROUP BY country ORDER BY country''')
        con.execute(f'''CREATE OR REPLACE TABLE coverage_s{source} AS SELECT source1_entity_id,
            count(*) AS truth_count,count_if(name_key_equal OR address_key_equal) AS recovered
            FROM pair_features GROUP BY source1_entity_id''')
        sample = records(con, f'''SELECT a.entity_id AS source1_entity_id,b.entity_id AS target_id,a.country,
            a.business_name AS s1_name,b.business_name AS target_name,a.business_address AS s1_address,
            b.business_address AS target_address,a.name_key AS s1_name_key,b.name_key AS target_name_key,
            a.address_key AS s1_address_key,b.address_key AS target_address_key
            FROM truth_pairs g JOIN train_source1 a ON g.source1_entity_id=a.entity_id
            JOIN train_source{source} b ON g.target_id=b.entity_id
            WHERE hash(g.source1_entity_id,g.target_id)%200=0''')
        summaries = []
        for country in sorted(set(r['country'] for r in sample)):
            group = [r for r in sample if r['country']==country]
            values = []
            for row in group:
                row['name_ratio'] = ratio(row['s1_name_key'],row['target_name_key'])
                row['name_token_set_ratio'] = token_set_ratio(row['s1_name_key'],row['target_name_key'])
                row['address_ratio'] = ratio(row['s1_address_key'],row['target_address_key']) if row['target_address_key'] else None
                values.append(row['name_ratio'])
            values.sort()
            summaries.append({'country': country, 'sample_pairs': len(group),
                'name_ratio_p10_p50_p90': [values[int((len(values)-1)*q)] for q in [.1,.5,.9]],
                'name_ratio_below_50': sum(v<50 for v in values)})
        report['pair_sample'][f'S{source}'] = {'method':'DuckDB hash(s1,target)%200=0; deterministic at pinned version; approximately 0.5% of positive pairs', 'summary':summaries}
        dump_csv(output/f'positive_pair_sample_s{source}.csv',sample)
        dump_json(output/'full_audit.json',report)
    report['exact_key_oracle'] = records(con, '''SELECT a.country,count(*) AS s1_entities,
        count_if(coalesce(b.truth_count,0)+coalesce(c.truth_count,0)=0) AS singletons,
        count_if(coalesce(b.recovered,0)+coalesce(c.recovered,0)=coalesce(b.truth_count,0)+coalesce(c.truth_count,0)) AS entities_all_links_retrieved_including_singletons,
        avg(CASE WHEN coalesce(b.truth_count,0)+coalesce(c.truth_count,0)=0 THEN 1.0 ELSE
            1.25*(coalesce(b.recovered,0)+coalesce(c.recovered,0)) /
            (coalesce(b.recovered,0)+coalesce(c.recovered,0)+0.25*(coalesce(b.truth_count,0)+coalesce(c.truth_count,0))) END) AS macro_f05_oracle_ceiling
        FROM train_source1 a LEFT JOIN coverage_s2 b ON a.entity_id=b.source1_entity_id
        LEFT JOIN coverage_s3 c ON a.entity_id=c.source1_entity_id GROUP BY a.country ORDER BY a.country''')
    report['exact_key_oracle_note'] = 'Unlimited country+exact normalized name OR nonempty address candidates, with a hypothetical perfect classifier; measured on all training labels, not a validation model score. Ignores practical block caps.'
    dump_csv(output/'file_country_profile.csv', [dict(file=k,**row) for k,rows in report['profiles'].items() for row in rows])
    dump_csv(output/'positive_pair_profile.csv',report['positive_pairs'])
    dump_csv(output/'match_count_distribution.csv',report['match_counts'])
    con.execute('CHECKPOINT')
    con.close()
    report['elapsed_seconds'] = round(time.time()-started,2)
    report['complete'] = True
    dump_json(output/'full_audit.json',report)
    print(json.dumps({'complete':True,'elapsed_seconds':report['elapsed_seconds'],'truth':report['truth_integrity'],'cross_split':report['cross_split'],'oracle':report['exact_key_oracle']},indent=2),flush=True)


if __name__ == '__main__':
    main()
