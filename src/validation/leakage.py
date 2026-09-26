"""Leakage and integrity checks for a fold manifest (all restated independently of ``splits.build_manifest``).

Each check returns (name, ok, detail). ``run_checks`` needs a DuckDB connection with the relations ``s1``, ``targets`` and ``truth_pairs``
(see ``splits.build_manifest``) and the path of the manifest. The independent recomputation uses hashlib only.
"""
from typing import List, Tuple

from . import splits
from .scorer import macro_f05_tables

Check = Tuple[str, bool, str]


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def run_checks(con, manifest: str, seed: str = splits.SEED, full_recompute: bool = True, stress_manifest: str = '',
               documented_singleton_fraction: float = 0.0558482) -> List[Check]:
    m = f"read_parquet('{manifest}')"
    out: List[Check] = []

    def add(name: str, ok: bool, detail: str = '') -> None:
        out.append((name, bool(ok), detail))

    n_q, n_t = _one(con, 'SELECT count(*) FROM s1'), _one(con, 'SELECT count(*) FROM targets')
    add('L1 every entity appears once: (role, entity_id) is unique',
        _one(con, f'SELECT count(*) = count(DISTINCT (role, entity_id)) FROM {m}'), f'{_one(con, f"SELECT count(*) FROM {m}"):,} rows')
    add('L2 the queries are exactly the training Source-1 entities',
        _one(con, f"SELECT count(*) FROM {m} WHERE role = 'query'") == n_q
        and _one(con, f"SELECT count(*) FROM {m} m WHERE role = 'query' AND entity_id NOT IN (SELECT entity_id FROM s1)") == 0, f'{n_q:,}')
    add('L3 the targets are exactly the training S2/S3 entities',
        _one(con, f"SELECT count(*) FROM {m} WHERE role = 'target'") == n_t
        and _one(con, f"SELECT count(*) FROM {m} WHERE role = 'target' AND entity_id NOT IN (SELECT entity_id FROM targets)") == 0, f'{n_t:,}')
    add('L4 fold values are dev | val | holdout only', _one(con, f"SELECT count(*) FROM {m} WHERE fold NOT IN ('dev', 'val', 'holdout')") == 0)
    v = _one(con, f"""SELECT count(*) FROM truth_pairs p JOIN {m} q ON q.role = 'query' AND q.entity_id = p.source1_entity_id
                      JOIN {m} t ON t.role = 'target' AND t.entity_id = p.target_id WHERE q.fold <> t.fold""")
    add('L5 no true link crosses folds (every labeled target is in its owner\'s fold)', v == 0, f'{v} violating links of {_one(con, "SELECT count(*) FROM truth_pairs"):,}')
    v = _one(con, f"""SELECT count(*) FROM {m} t JOIN truth_pairs p ON p.target_id = t.entity_id
                      WHERE t.role = 'target' AND (t.owner_id IS DISTINCT FROM p.source1_entity_id OR t.assignment <> 'owner')""")
    add('L6 manifest owner_id equals the ground-truth owner for every labeled target', v == 0, f'{v} mismatches')
    v = _one(con, f"SELECT count(*) FROM {m} WHERE role = 'target' AND assignment = 'unmatched_hash' AND entity_id IN (SELECT target_id FROM truth_pairs)")
    add('L7 no labeled target is treated as unmatched', v == 0)
    # proportions per stratum follow the floor rule exactly
    bad = _one(con, f"""SELECT count(*) FROM (
        SELECT stratum, count(*) sz, count(*) FILTER (WHERE fold = 'dev') d, count(*) FILTER (WHERE fold = 'val') v FROM {m}
        WHERE role = 'query' GROUP BY stratum)
        WHERE d <> sz * {splits.FRACTIONS[0]} // 10 OR d + v <> sz * {splits.FRACTIONS[1]} // 10""")
    add('L8 every (country, bucket) stratum of queries has exactly the 80/10/10 floor split', bad == 0, f'{bad} strata off')
    bad = _one(con, f"""SELECT count(*) FROM (
        SELECT stratum, count(*) sz, count(*) FILTER (WHERE fold = 'dev') d, count(*) FILTER (WHERE fold = 'val') v FROM {m}
        WHERE assignment = 'unmatched_hash' GROUP BY stratum)
        WHERE d <> sz * {splits.FRACTIONS[0]} // 10 OR d + v <> sz * {splits.FRACTIONS[1]} // 10""")
    add('L9 unmatched targets have exactly the 80/10/10 floor split per (country, source)', bad == 0, f'{bad} strata off')
    # independent recomputation (hashlib) of every query and unmatched-target assignment
    if full_recompute:
        rows = con.execute(f"SELECT entity_id, stratum, fold FROM {m} WHERE role = 'query'").fetchall()
        want = splits.assign_folds_python([(e, s) for e, s, _ in rows], 'query', seed)
        bad_q = sum(want[e] != f for e, _s, f in rows)
        rows = con.execute(f"SELECT entity_id, stratum, fold FROM {m} WHERE assignment = 'unmatched_hash'").fetchall()
        want = splits.assign_folds_python([(e, s) for e, s, _ in rows], 'target', seed)
        bad_t = sum(want[e] != f for e, _s, f in rows)
        add('L10 an independent hashlib recomputation reproduces every query and unmatched-target fold', bad_q == 0 and bad_t == 0, f'{bad_q} query, {bad_t} target differences')
    # the fold must not depend on the ID number: each fold's mean ID is within 4 standard errors of the overall mean
    stats = con.execute(f"""
        WITH x AS (SELECT fold, CAST(regexp_extract(entity_id, '([0-9]+)$', 1) AS DOUBLE) AS n FROM {m} WHERE role = 'query'),
             o AS (SELECT avg(n) mu, stddev_pop(n) sd FROM x)
        SELECT fold, count(*), avg(n), (avg(n) - any_value(o.mu)) / (any_value(o.sd) / sqrt(count(*))) AS z FROM x, o GROUP BY fold ORDER BY fold""").fetchall()
    add('L11 the fold does not track the ID number (fold mean ID within 4 standard errors of the overall mean)', all(abs(r[3]) < 4 for r in stats),
        ', '.join(f'{r[0]} z={r[3]:+.2f}' for r in stats))
    # scorer sanity on the manifest's own folds: the all-empty baseline equals the singleton fraction of each fold
    con.execute('CREATE OR REPLACE TEMP VIEW truth_qt AS SELECT source1_entity_id AS q, target_id AS t FROM truth_pairs')
    con.execute('CREATE OR REPLACE TEMP TABLE empty_pred (q VARCHAR, t VARCHAR)')
    for fold in splits.FOLDS + ('all',):
        where = '' if fold == 'all' else f"AND fold = '{fold}'"
        con.execute(f"CREATE OR REPLACE TEMP VIEW fold_q AS SELECT entity_id AS id FROM {m} WHERE role = 'query' {where}")
        if _one(con, 'SELECT count(*) FROM fold_q') == 0:
            add(f'L12 fold "{fold}" has queries', False, 'empty fold')
            continue
        score = macro_f05_tables(con, 'fold_q', 'truth_qt', 'empty_pred')
        single = _one(con, f"SELECT count(*) FROM {m} WHERE role = 'query' AND match_count = 0 {where}") / score['queries']
        add(f'L12 all-empty baseline on fold "{fold}" equals its singleton fraction', abs(score['macro_f05'] - single) < 1e-12, f"{score['macro_f05']:.7f} ({score['queries']:,} queries)")
    if documented_singleton_fraction is not None:
        add(f'L13 all-empty baseline on the full labeled set is the documented {documented_singleton_fraction}',
            abs(macro_f05_tables(con, '(SELECT entity_id AS id FROM s1)', 'truth_qt', 'empty_pred')['macro_f05'] - documented_singleton_fraction) < 5e-8)
    v = _one(con, f"SELECT count(*) FROM {m} WHERE fullcorpus_sample AND (role <> 'query' OR fold = 'dev')")
    add('L14 the full-corpus stress sample only contains held-out (val/holdout) queries', v == 0)
    if stress_manifest:
        s = f"read_parquet('{stress_manifest}')"
        add('L15 stress protocol: every group is inside one fold',
            _one(con, f"SELECT count(*) FROM (SELECT group_id FROM {s} WHERE role = 'query' GROUP BY group_id HAVING count(DISTINCT fold) > 1)") == 0)
        v = _one(con, f"""SELECT count(*) FROM truth_pairs p JOIN {s} q ON q.role = 'query' AND q.entity_id = p.source1_entity_id
                          JOIN {s} t ON t.role = 'target' AND t.entity_id = p.target_id WHERE q.fold <> t.fold""")
        add('L16 stress protocol: no true link crosses folds', v == 0, f'{v} violations')
        add('L17 stress protocol: same entities as the main protocol',
            _one(con, f"SELECT count(*) FROM {s}") == _one(con, f"SELECT count(*) FROM {m}"))
    return out
