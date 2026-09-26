"""Member B / B1: label integrity, slices and error taxonomy (training labels only).

    python scripts/label_summary.py

Reads the ground-truth TSV directly (independent of audit.duckdb), the frozen folds (if built) and the cleaned feature table. Writes
    reports/eda/label_summary.json, label_summary.md, label_error_taxonomy.csv       and    data/scratch/label_pairs.parquet
(pair-level flags reused by B3/B4). Nothing here is used to fit anything: it describes the labels and defines the error taxonomy.

Denominators: every slice states its own. S1 slices use the 2,206,821 reference queries (singletons included); pair slices use the
7,638,365 expanded positive links. Slice membership overlaps (a query can be both cross-script and number-conflicted).
"""
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / 'student_resource' / 'dataset' / 'train' / 'train_ground_truth.tsv'
FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0'
FOLDS = ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet'
OUT = ROOT / 'reports' / 'eda'
SCRATCH = ROOT / 'data' / 'scratch'
INDIC = 2 + 4 + 8 + 16 + 32 + 64 + 128 + 256 + 512      # bits 1..9 of name_scripts (translit.SCRIPT_BITS)
LOW_JW = 0.60                                             # name similarity below this is "low"
COMMON_NAME = 10                                          # a name_core shared by >= this many S1 records in a country is "common"

SCRIPT_NAME = ("CASE WHEN ({m} & 2) > 0 THEN 'Devanagari' WHEN ({m} & 4) > 0 THEN 'Bengali' WHEN ({m} & 8) > 0 THEN 'Gurmukhi' WHEN ({m} & 16) > 0 THEN 'Gujarati' "
               "WHEN ({m} & 32) > 0 THEN 'Oriya' WHEN ({m} & 64) > 0 THEN 'Tamil' WHEN ({m} & 128) > 0 THEN 'Telugu' WHEN ({m} & 256) > 0 THEN 'Kannada' "
               "WHEN ({m} & 512) > 0 THEN 'Malayalam' ELSE 'Other' END")


def script_class(m: str) -> str:
    return f"CASE WHEN ({m} & {INDIC}) = 0 THEN 'Latin' WHEN ({m} & 1) > 0 THEN 'Mixed' ELSE {SCRIPT_NAME.format(m=m)} END"


def pct(n, d):
    return f'{100 * n / d:.2f}%' if d else 'n/a'


def main() -> int:
    started = time.perf_counter()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='11GB'")
    feats = (FEATURES / 'split=train' / 'source=*' / 'country=*' / '*.parquet').as_posix()
    con.execute(f"""CREATE VIEW f AS SELECT entity_id, source, country, name_key, address_key, name_core, name_scripts, name_placeholder_like, address_missing,
                    address_canon, address_tokset, address_numbers_canon FROM read_parquet('{feats}', hive_partitioning=false)""")
    con.execute(f"CREATE VIEW truth AS SELECT * FROM read_csv('{TRUTH.as_posix()}', delim='\t', header=true, quote='', escape='', all_varchar=true)")
    report: dict = {}

    # ------------------------------------------------------------------ integrity (independent of audit.duckdb)
    con.execute("""CREATE TABLE pairs0 AS SELECT source1_entity_id AS q, trim(t) AS t FROM (
                     SELECT source1_entity_id, unnest(string_split(matched_entity_ids, ',')) AS t FROM truth) WHERE trim(t) <> ''""")
    n_rows, n_distinct = con.execute("SELECT count(*), count(DISTINCT source1_entity_id) FROM truth").fetchone()
    n_s1 = con.execute("SELECT count(*) FROM f WHERE source = 1").fetchone()[0]
    n_pairs, n_unique_pairs, n_targets = con.execute("SELECT count(*), count(DISTINCT (q, t)), count(DISTINCT t) FROM pairs0").fetchone()
    no_row = con.execute("SELECT count(*) FROM f WHERE source = 1 AND entity_id NOT IN (SELECT source1_entity_id FROM truth)").fetchone()[0]
    stray = con.execute("SELECT count(*) FROM truth WHERE source1_entity_id NOT IN (SELECT entity_id FROM f WHERE source = 1)").fetchone()[0]
    missing_target = con.execute("SELECT count(*) FROM pairs0 WHERE t NOT IN (SELECT entity_id FROM f WHERE source IN (2, 3))").fetchone()[0]
    wrong_source = con.execute("SELECT count(*) FROM pairs0 p JOIN f ON f.entity_id = p.t WHERE f.source <> CAST(substr(p.t, 2, 1) AS INTEGER)").fetchone()[0]
    multi_owner = con.execute("SELECT count(*) FROM (SELECT t FROM pairs0 GROUP BY t HAVING count(DISTINCT q) > 1)").fetchone()[0]
    country_mismatch = con.execute("SELECT count(*) FROM pairs0 p JOIN f a ON a.entity_id = p.q JOIN f b ON b.entity_id = p.t WHERE a.country <> b.country").fetchone()[0]
    singletons = con.execute("SELECT count(*) FROM truth WHERE matched_entity_ids IS NULL OR trim(matched_entity_ids) = ''").fetchone()[0]
    dup_tuple = con.execute("SELECT count(*) FROM (SELECT 1 FROM f WHERE source = 1 GROUP BY country, name_key, address_key HAVING count(*) > 1)").fetchone()[0]
    name_groups = con.execute("""SELECT country, count(*) FILTER (WHERE n > 1) AS groups_gt1, max(n) AS largest, sum(n) FILTER (WHERE n > 1) AS entities_in_shared_groups, sum(n) AS entities
                                 FROM (SELECT country, name_key, count(*) n FROM f WHERE source = 1 GROUP BY 1, 2) GROUP BY country ORDER BY country""").fetchall()
    integrity = {
        'truth_rows': n_rows, 'distinct_s1_in_truth': n_distinct, 'training_s1_entities': n_s1, 's1_without_truth_row': no_row, 'truth_rows_without_s1': stray,
        'singleton_queries': singletons, 'singleton_fraction': singletons / n_s1, 'positive_pairs': n_pairs, 'unique_pairs': n_unique_pairs, 'distinct_targets_linked': n_targets,
        'targets_missing_from_training_sources': missing_target, 'targets_in_wrong_source_table': wrong_source, 'targets_with_multiple_owners': multi_owner,
        'pairs_with_country_mismatch': country_mismatch, 'exact_duplicate_s1_tuples': dup_tuple,
        'name_key_groups': [{'country': c, 'groups_with_2plus_s1': g, 'largest_group': int(mx), 'entities_in_shared_groups': int(e or 0), 'entities': int(t),
                             'share_in_shared_groups': float((e or 0) / t)} for c, g, mx, e, t in name_groups]}
    assertions = {
        'one truth row per S1': n_rows == n_distinct == n_s1 and no_row == 0 and stray == 0, 'no duplicate pairs': n_pairs == n_unique_pairs,
        'every target exists in its own training source': missing_target == 0 and wrong_source == 0, 'one owner per target': multi_owner == 0,
        'country preserved on every link': country_mismatch == 0, 'no exact duplicate S1 tuples': dup_tuple == 0,
        'singleton queries equal S1 minus queries with links (123,247)': singletons == n_s1 - con.execute('SELECT count(DISTINCT q) FROM pairs0').fetchone()[0]}
    report['integrity'] = integrity
    report['integrity_assertions'] = assertions
    for name, ok in assertions.items():
        print(('PASS  ' if ok else 'FAIL  ') + name, flush=True)

    # ------------------------------------------------------------------ pair-level flags (reused by B3/B4)
    ind = INDIC
    con.execute(f"""
    CREATE TABLE label_pairs AS
    SELECT p.q, p.t, a.country, b.source AS tsrc,
           a.name_key = b.name_key AND a.name_key <> '' AS name_key_eq,
           a.address_key = b.address_key AND a.address_key <> '' AS addr_key_eq,
           a.name_core = b.name_core AND a.name_core <> '' AS core_eq,
           a.address_canon = b.address_canon AND a.address_canon <> '' AS canon_eq,
           jaro_winkler_similarity(a.name_core, b.name_core) AS jw,
           CASE WHEN len(a.toks) = 0 OR len(b.toks) = 0 THEN 0.0
                ELSE len(list_intersect(a.toks, b.toks))::DOUBLE / len(list_distinct(list_concat(a.toks, b.toks))) END AS addr_jaccard,
           b.address_missing AS tgt_addr_missing, a.address_missing AS s1_addr_missing,
           (b.name_scripts & {ind}) > 0 AND (a.name_scripts & {ind}) = 0 AS cross_script,
           {script_class('a.name_scripts')} || ' -> ' || {script_class('b.name_scripts')} AS script_pair,
           b.name_placeholder_like AS tgt_placeholder, a.name_placeholder_like AS s1_placeholder,
           len(a.address_numbers_canon) > 0 AND len(b.address_numbers_canon) > 0 AND NOT list_has_any(a.address_numbers_canon, b.address_numbers_canon) AS number_conflict
    FROM pairs0 p
    JOIN (SELECT *, string_split(address_tokset, ' ') AS toks FROM f WHERE source = 1) a ON a.entity_id = p.q
    JOIN (SELECT *, string_split(address_tokset, ' ') AS toks FROM f WHERE source IN (2, 3)) b ON b.entity_id = p.t""")
    con.execute("""ALTER TABLE label_pairs ADD COLUMN error_type VARCHAR""")
    con.execute("""UPDATE label_pairs SET error_type = CASE
        WHEN name_key_eq AND addr_key_eq THEN '01 exact name and address'
        WHEN name_key_eq THEN '02 exact name, address differs'
        WHEN addr_key_eq THEN '03 exact address, name differs'
        WHEN cross_script THEN '04 cross-script target name'
        WHEN tgt_placeholder THEN '05 placeholder target name (NA-style)'
        WHEN tgt_addr_missing THEN '06 target address missing'
        WHEN core_eq OR canon_eq THEN '07 equal after v2 cleaning (name_core or address_canon)'
        WHEN jw >= 0.85 OR addr_jaccard >= 0.8 THEN '08 fuzzy name or address'
        WHEN jw >= 0.60 OR addr_jaccard >= 0.5 THEN '09 weak partial evidence'
        ELSE '10 no shared textual evidence' END""")
    con.execute(f"COPY label_pairs TO '{(SCRATCH / 'label_pairs.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f'pair flags built ({time.perf_counter() - started:.0f}s)', flush=True)

    tax = con.execute("""SELECT error_type, country, tsrc, count(*) FROM label_pairs GROUP BY ALL ORDER BY 1, 2, 3""").fetchall()
    tot = {}
    for _e, c, s, n in tax:
        tot[(c, s)] = tot.get((c, s), 0) + n
    with (OUT / 'label_error_taxonomy.csv').open('w', encoding='utf-8', newline='\n') as fh:
        fh.write('error_type,country,target_source,links,share_of_country_source_links\n')
        for e, c, s, n in tax:
            fh.write(f'{e},{c},S{s},{n},{n / tot[(c, s)]:.6f}\n')
    report['pairs'] = n_pairs
    report['error_taxonomy'] = [{'error_type': e, 'country': c, 'target_source': f'S{s}', 'links': n, 'share': n / tot[(c, s)]} for e, c, s, n in tax]
    flag_rows = con.execute("""SELECT country, tsrc, count(*), count(*) FILTER (WHERE tgt_addr_missing), count(*) FILTER (WHERE cross_script), count(*) FILTER (WHERE tgt_placeholder),
                               count(*) FILTER (WHERE number_conflict), count(*) FILTER (WHERE jw < 0.6), count(*) FILTER (WHERE name_key_eq), count(*) FILTER (WHERE addr_key_eq)
                               FROM label_pairs GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    report['pair_flags'] = [dict(zip(['country', 'target_source', 'links', 'target_address_missing', 'cross_script', 'placeholder_target', 'number_conflict',
                                      f'name_similarity_below_{LOW_JW}', 'exact_name_key', 'exact_address_key'], r)) for r in flag_rows]
    script_rows = con.execute("SELECT script_pair, country, count(*) FROM label_pairs WHERE script_pair <> 'Latin -> Latin' GROUP BY ALL ORDER BY 3 DESC LIMIT 25").fetchall()
    report['script_pairs_non_latin'] = [{'script_pair': s, 'country': c, 'links': n} for s, c, n in script_rows]

    # ------------------------------------------------------------------ query-level slices
    fold_join = f"LEFT JOIN (SELECT entity_id, fold FROM read_parquet('{FOLDS.as_posix()}') WHERE role = 'query') fo ON fo.entity_id = s.entity_id" if FOLDS.exists() else ''
    fold_col = 'fo.fold' if FOLDS.exists() else "'n/a'"
    con.execute(f"""
    CREATE TABLE qslice AS
    WITH agg AS (SELECT q, count(*) n, count(*) FILTER (WHERE tsrc = 2) n2, count(*) FILTER (WHERE tsrc = 3) n3,
                        bool_or(tgt_addr_missing) any_addr_missing, bool_or(cross_script) any_cross, bool_or(tgt_placeholder OR s1_placeholder) any_placeholder,
                        bool_or(number_conflict) any_num_conflict, max(jw) best_jw, bool_or(name_key_eq OR addr_key_eq) any_exact
                 FROM label_pairs GROUP BY q),
         common AS (SELECT country, name_core, count(*) AS c FROM f WHERE source = 1 GROUP BY 1, 2)
    SELECT s.entity_id, s.country, {fold_col} AS fold, coalesce(a.n, 0) AS n,
           CASE WHEN coalesce(a.n, 0) = 0 THEN '0' WHEN a.n = 1 THEN '1' WHEN a.n = 2 THEN '2' WHEN a.n <= 4 THEN '3-4' ELSE '5+' END AS bucket,
           coalesce(a.n2, 0) > 0 AS has_s2, coalesce(a.n3, 0) > 0 AS has_s3, coalesce(a.any_addr_missing, false) AS any_addr_missing, coalesce(a.any_cross, false) AS any_cross,
           coalesce(a.any_placeholder, false) OR s.name_placeholder_like AS any_placeholder, coalesce(a.any_num_conflict, false) AS any_num_conflict,
           a.best_jw, a.n IS NOT NULL AND a.best_jw < {LOW_JW} AS all_names_low, coalesce(a.any_exact, false) AS any_exact, cm.c >= {COMMON_NAME} AS common_name,
           s.address_missing AS s1_addr_missing
    FROM (SELECT * FROM f WHERE source = 1) s {fold_join}
    LEFT JOIN agg a ON a.q = s.entity_id LEFT JOIN common cm ON cm.country = s.country AND cm.name_core = s.name_core""")
    slices = [('all queries', 'true'), ('singleton (0 true links)', 'n = 0'), ('has any link', 'n >= 1'),
              ('match count 1', "bucket = '1'"), ('match count 2', "bucket = '2'"), ('match count 3-4', "bucket = '3-4'"), ('match count 5+', "bucket = '5+'"),
              ('has an S2 target', 'has_s2'), ('has an S3 target', 'has_s3'), ('has both S2 and S3 targets', 'has_s2 AND has_s3'),
              ('a target address is missing', 'any_addr_missing'), ('S1 address missing', 's1_addr_missing'),
              ('a target name is in another script (cross-script)', 'any_cross'), ('a placeholder (NA-style) name is involved', 'any_placeholder'),
              (f'best target name similarity < {LOW_JW} (all targets low)', 'all_names_low'), ('a target has a conflicting number', 'any_num_conflict'),
              (f'common name (name_core shared by >= {COMMON_NAME} S1 records)', 'common_name'), ('no exact name_key or address_key match to any target', 'n >= 1 AND NOT any_exact')]
    table = []
    for label, cond in slices:
        for country in ('all', 'India', 'US'):
            where = cond if country == 'all' else f"({cond}) AND country = '{country}'"
            denom = n_s1 if country == 'all' else con.execute(f"SELECT count(*) FROM qslice WHERE country = '{country}'").fetchone()[0]
            k = con.execute(f'SELECT count(*), coalesce(sum(n), 0) FROM qslice WHERE {where}').fetchone()
            table.append({'slice': label, 'country': country, 'queries': k[0], 'share_of_country_queries': k[0] / denom, 'links': int(k[1]), 'denominator': denom})
    report['query_slices'] = table
    if FOLDS.exists():
        report['queries_by_fold'] = [dict(zip(['fold', 'country', 'queries', 'singletons', 'links'], r)) for r in con.execute(
            "SELECT fold, country, count(*), count(*) FILTER (WHERE n = 0), sum(n) FROM qslice GROUP BY 1, 2 ORDER BY 1, 2").fetchall()]
        report['slice_share_by_fold'] = [dict(zip(['fold', 'slice', 'share'], r)) for r in con.execute("""
            SELECT fold, s, avg(v::INT) FROM (
              SELECT fold, 'singleton' s, n = 0 v FROM qslice UNION ALL SELECT fold, 'has_s2', has_s2 FROM qslice UNION ALL SELECT fold, 'has_s3', has_s3 FROM qslice
              UNION ALL SELECT fold, 'cross_script', any_cross FROM qslice UNION ALL SELECT fold, 'target_address_missing', any_addr_missing FROM qslice
              UNION ALL SELECT fold, 'number_conflict', any_num_conflict FROM qslice UNION ALL SELECT fold, 'common_name', coalesce(common_name, false) FROM qslice
              UNION ALL SELECT fold, 'placeholder', any_placeholder FROM qslice) GROUP BY 1, 2 ORDER BY 2, 1""").fetchall()]

    (OUT / 'label_summary.json').write_text(json.dumps(report, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    md = ['# Label summary and error taxonomy (training labels)', '',
          'Generated by `scripts/label_summary.py`. Denominators are stated per row; slice membership overlaps. Nothing here is fitted to labels.', '',
          '## Integrity (recomputed from the ground-truth TSV)', '', '| check | value |', '|---|---:|']
    for k, v in integrity.items():
        if k != 'name_key_groups':
            md.append(f'| {k.replace("_", " ")} | {v:,} |' if isinstance(v, int) else f'| {k.replace("_", " ")} | {v:.7f} |')
    md += ['', '| assertion | result |', '|---|---|'] + [f'| {k} | {"PASS" if v else "**FAIL**"} |' for k, v in assertions.items()]
    md += ['', '## Query slices (denominator = S1 queries of the country; the "all" row uses all 2,206,821)', '', '| slice | country | queries | share | links |', '|---|---|---:|---:|---:|']
    md += [f'| {r["slice"]} | {r["country"]} | {r["queries"]:,} | {100 * r["share_of_country_queries"]:.2f}% | {r["links"]:,} |' for r in table]
    md += ['', '## Error taxonomy of the 7,638,365 true links (mutually exclusive, first matching rule wins)', '',
           'Read it as: how much evidence does the *pair* offer to an exact/cleaned/fuzzy channel. Categories 01-03 are what the v1 exact keys already recover; 07 is what cleaning v2 adds; 08-10 need fuzzy retrieval or a model.', '',
           '| error type | country | target | links | share of that country/source |', '|---|---|---|---:|---:|']
    md += [f'| {r["error_type"]} | {r["country"]} | S{r["target_source"][1:]} | {r["links"]:,} | {100 * r["share"]:.2f}% |' for r in report['error_taxonomy']]
    exact_links = sum(r['links'] for r in report['error_taxonomy'] if r['error_type'][:2] in ('01', '02', '03'))
    md += ['', '## Reconciliation with the earlier audit', '',
           f'* Links recovered by an exact name_key or address_key (categories 01-03): {exact_links:,} = **{100 * exact_links / n_pairs:.2f}%** of all links (the audit reports 28.80% link recall for the exact-key oracle).',
           f'* Singletons {singletons:,} = {100 * singletons / n_s1:.4f}% of queries: the all-empty prediction scores {singletons / n_s1:.7f} (documented 0.0558482).',
           f'* Positive links {n_pairs:,}, one owner per target, country preserved: identical to the audit label-integrity block.']
    if 'slice_share_by_fold' in report:
        md += ['', "## Slice balance across the frozen folds (share of each fold's queries)", '', '| slice | dev | val | holdout |', '|---|---:|---:|---:|']
        by = {}
        for r in report['slice_share_by_fold']:
            by.setdefault(r['slice'], {})[r['fold']] = r['share']
        md += [f'| {k} | ' + ' | '.join(f"{100 * v.get(f, 0):.2f}%" for f in ('dev', 'val', 'holdout')) + ' |' for k, v in by.items()]
    (OUT / 'label_summary.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    print(f'done in {time.perf_counter() - started:.0f}s; all assertions pass: {all(assertions.values())}')
    return 0 if all(assertions.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
