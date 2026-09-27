"""Candidate sets -> labeled, featurised pair tables (B6).

1. ``aggregate_candidates``: one row per (query, target) in the ``candidate_v1`` contract of src/modeling (channels, scores, ranks, block size,
   query candidate count, evidence stratum, label).  Labels come from the ground truth and are attached ONLY here, after retrieval.
2. ``build_pairs``: the 39 base features of ``modeling.pair_features`` (name/address/number/script similarities) plus retrieval-provenance extras
   (per-channel rank and score, relative scores, channel counts) into one Parquet table.
"""
import shutil
import sys
from pathlib import Path
from typing import Dict, List

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from modeling import pair_features as base  # noqa: E402
from modeling.contracts import CANDIDATE_CONTRACT_VERSION  # noqa: E402
from retrieval import engine  # noqa: E402

CHANNELS: List[str] = [c['name'] for c in engine.EQUALITY_CHANNELS] + [c['name'] for c in engine.POSTINGS_CHANNELS]
SPARSE = [c['name'] for c in engine.POSTINGS_CHANNELS]
RELATIVE = ['tok_name', 'tri_name', 'tok_address', 'bigram_address']

EXTRA_FEATURES: List[str] = ([f'rank_{c}' for c in CHANNELS] + [f'score_{c}' for c in CHANNELS] + [f'rel_{c}' for c in RELATIVE]
                             + ['n_eq_channels', 'n_sparse_channels', 'max_eq_block', 'best_sparse_rank'])
MODEL_FEATURES: List[str] = list(base.FEATURE_COLUMNS) + EXTRA_FEATURES
# variant with the embedding channel (LaBSE name similarity retrieval): rank, cosine score and the score relative to the query's best
EMB_FEATURES: List[str] = ['rank_emb_name', 'score_emb_name', 'rel_emb_name']
MODEL_FEATURES_E: List[str] = MODEL_FEATURES + EMB_FEATURES
STRATA = ['exact_v1_key', 'cleaned_equal', 'skeleton_or_secondary', 'sparse_name', 'sparse_address_only']

FORBIDDEN = base.FORBIDDEN_MODEL_COLUMNS | {'evidence_slice', 'stratum', 'query_id', 'target_id', 'q', 't'}


def assert_model_features(columns) -> List[str]:
    columns = list(columns)
    bad = set(columns) & FORBIDDEN
    unknown = set(columns) - set(MODEL_FEATURES_E)
    if bad or unknown or len(set(columns)) != len(columns):
        raise ValueError(f'unsafe or unknown model features: forbidden={sorted(bad)} unknown={sorted(unknown)}')
    return columns


def _conform_schema(path: str) -> None:
    """Rewrite the DuckDB output with the exact (non-nullable, float32/int32) Arrow schema of the candidate_v1 contract, streaming."""
    import pyarrow.parquet as pq
    from modeling.contracts import CANDIDATE_SCHEMA
    tmp = path + '.tmp'
    reader = pq.ParquetFile(path)
    writer = pq.ParquetWriter(tmp, CANDIDATE_SCHEMA, compression='zstd')
    for batch in reader.iter_batches(batch_size=500_000):
        import pyarrow as pa
        writer.write_table(pa.Table.from_batches([batch]).select(CANDIDATE_SCHEMA.names).cast(CANDIDATE_SCHEMA))
    writer.close()
    reader.close()                                   # release the source file before replacing it (Windows)
    Path(tmp).replace(path)


SHARDS = 6


def _shard_of(ids, n: int):
    import zlib
    import numpy as np
    return np.fromiter((zlib.crc32(x.encode()) % n for x in ids), dtype=np.int64, count=len(ids))


def shard_candidates(candidate_v1: str, shard_dir: str, n: int) -> list:
    """Split the candidate_v1 table by query (crc32 of the S1 id) so shards can be featurised in parallel; all pairs of a query stay together."""
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    from modeling.contracts import CANDIDATE_SCHEMA
    Path(shard_dir).mkdir(parents=True, exist_ok=True)
    paths = [Path(shard_dir) / f'cand_shard_{i}.parquet' for i in range(n)]
    writers = [pq.ParquetWriter(p, CANDIDATE_SCHEMA, compression='zstd') for p in paths]
    for batch in pq.ParquetFile(candidate_v1).iter_batches(batch_size=500_000):
        table = pa.Table.from_batches([batch])
        code = _shard_of(table.column('s1_entity_id').to_numpy(zero_copy_only=False), n)
        for i in range(n):
            mask = code == i
            if mask.any():
                writers[i].write_table(table.filter(pa.array(mask)))
    for w in writers:
        w.close()
    return [str(p) for p in paths]


def _featurise_shard(args):
    """Featurise one shard: first copy only the feature rows this shard needs (its queries and candidate targets) into a small Parquet folder, so the
    join inside ``build_pair_table`` never scans the full feature table. ``args`` is (feature_root, shard_path, out_path, shard_memory, validate)."""
    feature_root, shard, out, shard_memory, validate = args
    if Path(out).exists():
        Path(out).unlink()
    sub = Path(out).with_suffix('.feat')
    sub.mkdir(parents=True, exist_ok=True)
    fields = ', '.join(('entity_id', 'country') + tuple(base._RECORD_FIELDS))
    con = duckdb.connect()
    con.execute(f"SET threads=2; SET memory_limit='{shard_memory}'; SET preserve_insertion_order=false")
    con.execute(f"""COPY (SELECT {fields} FROM read_parquet('{(Path(feature_root) / '**' / '*.parquet').as_posix()}', hive_partitioning=false)
                     WHERE entity_id IN (SELECT s1_entity_id FROM read_parquet('{Path(shard).as_posix()}') UNION SELECT candidate_entity_id FROM read_parquet('{Path(shard).as_posix()}')))
                TO '{(sub / 'records.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    con.close()
    rows = base.build_pair_table(sub, shard, out, threads=2, validate=validate)['pair_rows']
    shutil.rmtree(sub, ignore_errors=True)
    return rows


def aggregate_candidates(cand_parquet: str, queries_parquet: str, out_parquet: str, truth_parquet: str = '', threads: int = 4, memory: str = '12GB') -> Dict[str, int]:
    """Write the candidate_v1 table. ``truth_parquet`` (columns q, t) labels the pairs (is_positive 1/0); without it is_positive = -1 (inference).
    Raise ``threads``/``memory`` for a large (test-scale) candidate table; the 12GB/4-thread default suits the ~15M-pair training scale."""
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='{memory}'; SET preserve_insertion_order=false")
    (ROOT / 'data' / 'scratch' / 'duckdb_tmp').mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(ROOT / 'data' / 'scratch' / 'duckdb_tmp').as_posix()}'")
    label = ("CASE WHEN tr.t IS NULL THEN 0 ELSE 1 END" if truth_parquet else '-1')
    join = f"LEFT JOIN read_parquet('{truth_parquet}') tr ON tr.q = a.q AND tr.t = a.t" if truth_parquet else ''
    strata = ("CASE WHEN list_has_any(chs, ['eq_name_key', 'eq_address_key']) THEN 'exact_v1_key' "
              "WHEN list_has_any(chs, ['eq_name_core', 'eq_name_compact', 'eq_address_tokset']) THEN 'cleaned_equal' "
              "WHEN list_has_any(chs, ['eq_name_skeleton', 'eq_core_postal', 'eq_core_number', 'eq_skeleton_number']) THEN 'skeleton_or_secondary' "
              "WHEN list_has_any(chs, ['tok_name', 'tri_name']) THEN 'sparse_name' ELSE 'sparse_address_only' END")
    con.execute(f"""
    COPY (
      WITH c AS (SELECT q, t, channel, rnk, score, blk FROM read_parquet('{cand_parquet}')),
           g AS (SELECT q, t, list(channel ORDER BY channel) AS chs, list(score::FLOAT ORDER BY channel) AS scs, list(rnk::INT ORDER BY channel) AS rks,
                        coalesce(max(blk) FILTER (WHERE channel LIKE 'eq_%'), 0)::INT AS block FROM c GROUP BY q, t),
           n AS (SELECT q, count(*)::INT AS qn FROM g GROUP BY q)
      SELECT a.q AS s1_entity_id, a.t AS candidate_entity_id, qs.country, '{CANDIDATE_CONTRACT_VERSION}' AS candidate_version,
             a.chs AS retrieval_channels, a.scs AS retrieval_scores, a.rks AS retrieval_ranks, a.block AS candidate_block_size, n.qn AS query_candidate_count,
             {strata} AS evidence_slice, ({label})::TINYINT AS is_positive, 1.0::FLOAT AS sample_weight
      FROM g a JOIN n USING (q) JOIN read_parquet('{queries_parquet}') qs ON qs.id = a.q {join}
      ) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    con.close()                       # Windows keeps the DuckDB output file locked until the connection is closed
    _conform_schema(out_parquet)
    con = duckdb.connect()
    r = con.execute(f"SELECT count(*), count(DISTINCT s1_entity_id), sum(is_positive) FILTER (WHERE is_positive = 1) FROM read_parquet('{out_parquet}')").fetchone()
    return {'pairs': r[0], 'queries_with_candidates': r[1], 'positives': int(r[2] or 0)}


def extras_sql(cand_parquet: str, with_emb: bool = False) -> str:
    """SQL producing (q, t, <EXTRA_FEATURES> [+ EMB_FEATURES]) from the raw per-channel candidate rows."""
    channels = CHANNELS + (['emb_name'] if with_emb else [])
    relative = RELATIVE + (['emb_name'] if with_emb else [])
    cols = []
    for ch in CHANNELS:
        cols.append(f"coalesce(max(rnk) FILTER (WHERE channel = '{ch}'), 101)::FLOAT AS rank_{ch}")
        cols.append(f"coalesce(max(score) FILTER (WHERE channel = '{ch}'), 0)::FLOAT AS score_{ch}")
    eq = "channel LIKE 'eq_%'"
    sp = "channel NOT LIKE 'eq_%' AND channel <> 'emb_name'"
    cols += [f"count(*) FILTER (WHERE {eq})::FLOAT AS n_eq_channels", f"count(*) FILTER (WHERE {sp})::FLOAT AS n_sparse_channels",
             f"coalesce(max(blk) FILTER (WHERE {eq}), 0)::FLOAT AS max_eq_block", f"coalesce(min(rnk) FILTER (WHERE {sp}), 101)::FLOAT AS best_sparse_rank"]
    if with_emb:
        cols += ["coalesce(max(rnk) FILTER (WHERE channel = 'emb_name'), 101)::FLOAT AS rank_emb_name", "coalesce(max(score) FILTER (WHERE channel = 'emb_name'), 0)::FLOAT AS score_emb_name"]
    rel = ', '.join(f"coalesce(max(score) FILTER (WHERE channel = '{ch}') / nullif(max(max(score) FILTER (WHERE channel = '{ch}')) OVER (PARTITION BY q), 0), 0)::FLOAT AS rel_{ch}"
                    for ch in relative)
    return f"SELECT q, t, {', '.join(cols)}, {rel} FROM read_parquet('{cand_parquet}') GROUP BY q, t"


def build_pairs(cand_parquet: str, candidate_v1_parquet: str, feature_root: str, out_parquet: str, workdir: str, threads: int = 6, with_emb: bool = False,
               shards: int = SHARDS, workers: int = 4, memory: str = '12GB', shard_memory: str = '2500MB', validate: bool = True) -> Dict[str, int]:
    """Base pair features (modeling.pair_features.build_pair_table, run on query-disjoint shards in parallel processes) joined with the retrieval
    extras -> ``out_parquet``. On a bigger machine raise ``shards`` and ``workers`` together (one process per shard) and ``memory`` for the final join."""
    from concurrent.futures import ProcessPoolExecutor
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    shard_paths = shard_candidates(candidate_v1_parquet, (work / 'shards').as_posix(), shards)
    jobs = [(feature_root, sh, (work / f'base_{i}.parquet').as_posix(), shard_memory, validate) for i, sh in enumerate(shard_paths)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_featurise_shard, jobs))
    total_candidates = duckdb.connect().execute(f"SELECT count(*) FROM read_parquet('{candidate_v1_parquet}')").fetchone()[0]
    if sum(rows) != total_candidates:
        raise RuntimeError(f'sharded featurisation lost pairs: {sum(rows)} of {total_candidates}')
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='{memory}'; SET preserve_insertion_order=false")
    (ROOT / 'data' / 'scratch' / 'duckdb_tmp').mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(ROOT / 'data' / 'scratch' / 'duckdb_tmp').as_posix()}'")
    keep = ', '.join(f'p.{c}' for c in ('s1_entity_id', 'candidate_entity_id', 'country', 'evidence_slice', 'is_positive') + tuple(base.FEATURE_COLUMNS))
    ex = ', '.join(f'e.{c}' for c in (MODEL_FEATURES_E[len(base.FEATURE_COLUMNS):] if with_emb else EXTRA_FEATURES))
    con.execute(f"""
    COPY (SELECT {keep}, {ex} FROM read_parquet('{(work / 'base_*.parquet').as_posix()}') p
          JOIN ({extras_sql(cand_parquet, with_emb)}) e ON e.q = p.s1_entity_id AND e.t = p.candidate_entity_id
          ) TO '{out_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{out_parquet}')").fetchone()[0]
    if n != total_candidates:
        raise RuntimeError(f'extras join changed the row count: {total_candidates} -> {n}')
    shutil.rmtree(work, ignore_errors=True)
    return {'pairs': n, 'features': len(MODEL_FEATURES_E if with_emb else MODEL_FEATURES)}
