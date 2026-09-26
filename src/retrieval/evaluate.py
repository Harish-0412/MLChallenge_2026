"""Candidate-set metrics (B3/B5). The only place where labels meet candidates.

Required relations in the connection: ``cand(channel, q, t, rnk, score)`` (entity ids), ``bench_q(id, country, ...)`` (every evaluated query,
singletons included) and ``truth(q, t)`` (positive links of those queries).
"""
from typing import Dict, Iterable, Mapping

from validation.scorer import macro_f05_tables


def spec_condition(spec: Mapping[str, int]) -> str:
    """{'channel': k} -> SQL condition selecting rank <= k of each listed channel."""
    return ' OR '.join(f"(channel = '{c}' AND rnk <= {int(k)})" for c, k in spec.items()) or 'false'


def evaluate(con, spec: Mapping[str, int], country: str = 'all') -> Dict[str, float]:
    where_q = '' if country == 'all' else f"WHERE country = '{country}'"
    con.execute(f"CREATE OR REPLACE TEMP TABLE _qs AS SELECT id FROM bench_q {where_q}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE _sel AS SELECT DISTINCT q, t FROM cand WHERE ({spec_condition(spec)}) AND q IN (SELECT id FROM _qs)")
    con.execute("CREATE OR REPLACE TEMP TABLE _tr AS SELECT q, t FROM truth WHERE q IN (SELECT id FROM _qs)")
    con.execute("""
    CREATE OR REPLACE TEMP TABLE _per AS
    SELECT s.id, coalesce(tn.n, 0) AS n_true, coalesce(cn.n, 0) AS n_cand, coalesce(h.n, 0) AS n_hit
    FROM _qs s LEFT JOIN (SELECT q, count(*) n FROM _tr GROUP BY q) tn ON tn.q = s.id
         LEFT JOIN (SELECT q, count(*) n FROM _sel GROUP BY q) cn ON cn.q = s.id
         LEFT JOIN (SELECT q, count(*) n FROM _sel JOIN _tr USING (q, t) GROUP BY q) h ON h.q = s.id""")
    r = con.execute("""
    SELECT count(*), sum(n_true), sum(n_hit), sum(n_cand),
           avg(n_hit::DOUBLE / n_true) FILTER (WHERE n_true > 0), avg((n_hit = n_true)::INT) FILTER (WHERE n_true > 0),
           avg((n_cand = 0)::INT), avg(n_cand), quantile_cont(n_cand, 0.5), quantile_cont(n_cand, 0.9), quantile_cont(n_cand, 0.99), max(n_cand),
           avg(CASE WHEN n_true = 0 THEN 1.0 ELSE 1.25 * n_hit / (1.25 * n_hit + 0.25 * (n_true - n_hit)) END),
           count(*) FILTER (WHERE n_true = 0)
    FROM _per""").fetchone()
    queries, links, hits, pairs = r[0], int(r[1]), int(r[2]), int(r[3])
    # oracle through the shared scorer as a cross-check of the closed form above
    con.execute("CREATE OR REPLACE TEMP TABLE _oracle AS SELECT q, t FROM _sel JOIN _tr USING (q, t)")
    scored = macro_f05_tables(con, '_qs', '_tr', '_oracle')['macro_f05']
    assert abs(scored - r[12]) < 1e-9, (scored, r[12])
    return {'queries': queries, 'singletons': int(r[13]), 'links': links, 'hits': hits, 'micro_recall': hits / links if links else float('nan'),
            'macro_recall_nonsingleton': r[4], 'all_links_coverage': r[5], 'zero_candidate_rate': r[6], 'pairs': pairs, 'cand_mean': r[7],
            'cand_p50': r[8], 'cand_p90': r[9], 'cand_p99': r[10], 'cand_max': int(r[11]), 'precision_proxy': hits / pairs if pairs else float('nan'),
            'oracle_macro_f05': r[12]}


def missed_by_slice(con, spec: Mapping[str, int], flags_parquet: str) -> list:
    """Missed true links grouped by error type and slice flags (flags come from data/scratch/label_pairs.parquet)."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE _sel AS SELECT DISTINCT q, t FROM cand WHERE {spec_condition(spec)}")
    rows = con.execute(f"""
    WITH lp AS (SELECT p.q, p.t, p.country, p.tsrc, p.error_type, p.cross_script, p.tgt_addr_missing, p.number_conflict, p.jw < 0.6 AS low_name_sim
                FROM read_parquet('{flags_parquet}') p WHERE p.q IN (SELECT id FROM bench_q)),
         m AS (SELECT lp.*, (s.q IS NOT NULL) AS found FROM lp LEFT JOIN _sel s ON s.q = lp.q AND s.t = lp.t)
    SELECT dim, val, count(*) AS links, count(*) FILTER (WHERE NOT found) AS missed FROM (
        SELECT 'error_type' AS dim, error_type AS val, found FROM m UNION ALL SELECT 'country', country, found FROM m
        UNION ALL SELECT 'target_source', 'S' || tsrc, found FROM m UNION ALL SELECT 'cross_script', cross_script::VARCHAR, found FROM m
        UNION ALL SELECT 'target_address_missing', tgt_addr_missing::VARCHAR, found FROM m UNION ALL SELECT 'number_conflict', number_conflict::VARCHAR, found FROM m
        UNION ALL SELECT 'low_name_similarity', low_name_sim::VARCHAR, found FROM m UNION ALL SELECT 'all links', 'all', found FROM m)
    GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    return [{'dimension': d, 'value': v, 'links': int(n), 'missed': int(x), 'recall': 1 - x / n} for d, v, n, x in rows]
