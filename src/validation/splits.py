"""Deterministic 80/10/10 validation folds (protocol ``val_v1``).

Unit of assignment: one Source-1 identity group. Every true S2/S3 target follows its owner; unmatched targets are assigned by the same rule
within (country, source). The assignment is a pure function of (SEED, entity id, country, match-count bucket):

    hash    = sha256("<SEED>|<role>|<entity_id>")                      (hex string; ties broken by entity id)
    rank    = position of the entity when its stratum is sorted by (hash, entity_id), 1-based
    n       = size of the stratum
    fold    = dev      if rank <= floor(8n/10)
              val      if rank <= floor(9n/10)
              holdout  otherwise

Strata: query = (country, bucket of the number of true targets: 0, 1, 2, 3-4, 5+); unmatched target = (country, source).
Nothing else (labels of other entities, text, ID magnitude) influences an assignment. ``assign_folds_python`` recomputes the same rule with
hashlib only, so the manifest can be verified without DuckDB.

Stress protocol (``stress_name_v1``): Source-1 entities that share (country, name_key) form one group and are assigned together (a common
business name can never be split between dev and holdout); groups are ranked within country (fold sizes are therefore approximate at the entity level; the report states the balance).
"""
import hashlib
from typing import Dict, List, Tuple

SEED = 'mlch2026-val-v1'
FRACTIONS = (8, 9)               # cut points out of 10: dev <= 8/10, val <= 9/10, rest holdout
BUCKETS = ('0', '1', '2', '3-4', '5+')
FOLDS = ('dev', 'val', 'holdout')
FULLCORPUS_SAMPLE = 20_000       # held-out queries per (fold, country) used for the full-corpus stress protocol

BUCKET_SQL = "CASE WHEN n = 0 THEN '0' WHEN n = 1 THEN '1' WHEN n = 2 THEN '2' WHEN n <= 4 THEN '3-4' ELSE '5+' END"


def bucket_of(n: int) -> str:
    return '0' if n == 0 else '1' if n == 1 else '2' if n == 2 else '3-4' if n <= 4 else '5+'


def fold_of_rank(rank: int, size: int) -> str:
    if rank <= size * FRACTIONS[0] // 10:
        return 'dev'
    return 'val' if rank <= size * FRACTIONS[1] // 10 else 'holdout'


def hash_hex(role: str, entity_id: str, seed: str = SEED) -> str:
    return hashlib.sha256(f'{seed}|{role}|{entity_id}'.encode('utf-8')).hexdigest()


def assign_folds_python(entities: List[Tuple[str, str]], role: str, seed: str = SEED) -> Dict[str, str]:
    """Independent implementation of the rule. ``entities`` = [(entity_id, stratum)] -> {entity_id: fold}."""
    by_stratum: Dict[str, List[Tuple[str, str]]] = {}
    for entity_id, stratum in entities:
        by_stratum.setdefault(stratum, []).append((hash_hex(role, entity_id, seed), entity_id))
    out: Dict[str, str] = {}
    for stratum, members in by_stratum.items():
        members.sort()
        size = len(members)
        for rank, (_h, entity_id) in enumerate(members, 1):
            out[entity_id] = fold_of_rank(rank, size)
    return out


def _fold_case(rk: str = 'rk', sz: str = 'sz') -> str:
    return (f"CASE WHEN {rk} <= {sz} * {FRACTIONS[0]} // 10 THEN 'dev' WHEN {rk} <= {sz} * {FRACTIONS[1]} // 10 THEN 'val' ELSE 'holdout' END")


def build_manifest(con, out_parquet: str, seed: str = SEED, fullcorpus_sample: int = FULLCORPUS_SAMPLE) -> Dict[str, int]:
    """Write the fold manifest.

    Required relations in ``con``: ``s1(entity_id, country)`` (training Source-1 entities), ``targets(entity_id, source, country)``
    (training S2/S3 entities) and ``truth_pairs(source1_entity_id, target_id)``.
    """
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE q_folds AS
    WITH mc AS (SELECT s.entity_id, s.country, coalesce(t.n, 0) AS n FROM s1 s
                LEFT JOIN (SELECT source1_entity_id AS id, count(*) AS n FROM truth_pairs GROUP BY 1) t ON t.id = s.entity_id),
         b AS (SELECT *, {BUCKET_SQL} AS bucket, sha256('{seed}|query|' || entity_id) AS h FROM mc),
         r AS (SELECT *, row_number() OVER (PARTITION BY country, bucket ORDER BY h, entity_id) AS rk,
                         count(*) OVER (PARTITION BY country, bucket) AS sz FROM b)
    SELECT entity_id, country, n AS match_count, bucket, country || '|' || bucket AS stratum, {_fold_case()} AS fold, h FROM r""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE t_unmatched AS
    WITH u AS (SELECT t.entity_id, t.source, t.country, sha256('{seed}|target|' || t.entity_id) AS h FROM targets t
               WHERE t.entity_id NOT IN (SELECT target_id FROM truth_pairs)),
         r AS (SELECT *, row_number() OVER (PARTITION BY country, source ORDER BY h, entity_id) AS rk,
                         count(*) OVER (PARTITION BY country, source) AS sz FROM u)
    SELECT entity_id, source, country, {_fold_case()} AS fold FROM r""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE fc AS
    SELECT entity_id, row_number() OVER (PARTITION BY fold, country ORDER BY sha256('{seed}|fullcorpus|' || entity_id), entity_id) <= {fullcorpus_sample}
           AND fold <> 'dev' AS fullcorpus_sample FROM q_folds""")
    con.execute(f"""
    COPY (
      SELECT q.entity_id, 'query' AS role, 1::TINYINT AS source, q.country, q.fold, q.stratum, q.match_count,
             CAST(NULL AS VARCHAR) AS owner_id, 'stratified_hash' AS assignment, f.fullcorpus_sample
      FROM q_folds q JOIN fc f USING (entity_id)
      UNION ALL
      SELECT t.entity_id, 'target', t.source::TINYINT, t.country, o.fold, o.stratum, NULL, p.source1_entity_id, 'owner', false
      FROM targets t JOIN truth_pairs p ON p.target_id = t.entity_id JOIN q_folds o ON o.entity_id = p.source1_entity_id
      UNION ALL
      SELECT u.entity_id, 'target', u.source::TINYINT, u.country, u.fold, u.country || '|source' || u.source, NULL, NULL, 'unmatched_hash', false
      FROM t_unmatched u
      ORDER BY role, entity_id
    ) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    return dict(con.execute(f"SELECT fold, count(*) FROM read_parquet('{out_parquet}') GROUP BY fold").fetchall())


def build_stress_manifest(con, out_parquet: str, seed: str = SEED) -> Dict[str, int]:
    """Second protocol: S1 entities sharing (country, name_key) are one group. Requires ``s1_keys(entity_id, country, name_key)`` and the
    ``q_folds`` temp table of ``build_manifest`` (for match counts). Targets follow their owner; unmatched targets keep the main assignment."""
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE groups AS
    SELECT k.country, k.name_key, min(k.entity_id) AS group_id, count(*) AS group_size,
           sha256('{seed}|stressgroup|' || k.country || '|' || k.name_key) AS h
    FROM s1_keys k JOIN q_folds q USING (entity_id) GROUP BY k.country, k.name_key""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE g_folds AS
    WITH r AS (SELECT *, row_number() OVER (PARTITION BY country ORDER BY h, group_id) AS rk, count(*) OVER (PARTITION BY country) AS sz FROM groups)
    SELECT country, name_key, group_id, group_size, {_fold_case()} AS fold FROM r""")
    con.execute(f"""
    COPY (
      SELECT k.entity_id, 'query' AS role, 1::TINYINT AS source, k.country, g.fold, g.group_id, g.group_size, CAST(NULL AS VARCHAR) AS owner_id
      FROM s1_keys k JOIN g_folds g ON g.country = k.country AND g.name_key = k.name_key
      UNION ALL
      SELECT t.entity_id, 'target', t.source::TINYINT, t.country, g.fold, g.group_id, g.group_size, p.source1_entity_id
      FROM targets t JOIN truth_pairs p ON p.target_id = t.entity_id JOIN s1_keys k ON k.entity_id = p.source1_entity_id
      JOIN g_folds g ON g.country = k.country AND g.name_key = k.name_key
      UNION ALL
      SELECT u.entity_id, 'target', u.source::TINYINT, u.country, u.fold, NULL, NULL, NULL FROM t_unmatched u
      ORDER BY role, entity_id
    ) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    return dict(con.execute(f"SELECT fold, count(*) FROM read_parquet('{out_parquet}') GROUP BY fold").fetchall())
