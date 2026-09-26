"""Corpus loading, benchmark-query sampling and the two channel kinds (equality blocks and IDF-weighted token postings)."""
import hashlib
import time
from typing import Dict, List, Optional

from . import MAX_K

SEED = 'mlch2026-bench-v1'
FEATURE_COLUMNS = ['entity_id', 'country', 'name_key', 'address_key', 'name_core', 'name_core_compact', 'name_skeleton', 'name_translit',
                   'address_canon', 'address_tokset', 'address_postal_candidates', 'address_numbers_canon', 'address_missing']

# Derived columns shared by queries and targets (same expressions on both sides).
DERIVED = {
    'n_toks': "list_filter(list_distinct(string_split(name_translit, ' ')), x -> x <> '')",
    'n_tri': "CASE WHEN length(replace(name_translit, ' ', '')) < 3 THEN []::VARCHAR[] ELSE list_distinct(list_transform(range(0, least(length(replace(name_translit, ' ', '')), 40) - 2), "
             "i -> substr(replace(name_translit, ' ', ''), i + 1, 3))) END",
    'a_toks': "list_filter(list_distinct(string_split(address_tokset, ' ')), x -> x <> '')",
    'a_bi': "list_distinct(list_transform(range(1, len(string_split(address_canon, ' '))), "
            "i -> string_split(address_canon, ' ')[i] || '_' || string_split(address_canon, ' ')[i + 1]))",
    'postal1': "address_postal_candidates[1]",
    'num1': "address_numbers_canon[1]",
}


def sample_queries(con, manifest: str, n: int = 10_000, seed: str = SEED) -> str:
    """Deterministic stratified sample of dev queries (country x match-count bucket, proportional, largest-remainder rounding).

    Creates the temp table ``bench_q(id, country, stratum, match_count)`` and returns a content digest.
    """
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE bench_q AS
    WITH d AS (SELECT entity_id AS id, country, stratum, match_count, sha256('{seed}|bench|' || entity_id) AS h
               FROM read_parquet('{manifest}') WHERE role = 'query' AND fold = 'dev'),
         s AS (SELECT stratum, count(*) AS sz FROM d GROUP BY 1),
         tot AS (SELECT sum(sz) AS total FROM s),
         quota AS (SELECT stratum, floor({n} * sz::DOUBLE / total)::INT AS q0, ({n} * sz::DOUBLE / total) - floor({n} * sz::DOUBLE / total) AS frac
                   FROM s, tot),
         extra AS (SELECT stratum, q0 + CASE WHEN row_number() OVER (ORDER BY frac DESC, stratum) <= ({n} - (SELECT sum(q0) FROM quota)) THEN 1 ELSE 0 END AS quota
                   FROM quota),
         r AS (SELECT d.*, row_number() OVER (PARTITION BY d.stratum ORDER BY h, id) AS rk FROM d)
    SELECT r.id, r.country, r.stratum, r.match_count FROM r JOIN extra USING (stratum) WHERE r.rk <= extra.quota""")
    rows = con.execute("SELECT id FROM bench_q ORDER BY id").fetchall()
    return hashlib.sha256(','.join(r[0] for r in rows).encode()).hexdigest()


def load_corpus(con, feature_glob: str, manifest: str, country: str, fold: str = 'dev') -> Dict[str, int]:
    """Create ``bq`` (benchmark queries of the country) and ``tt`` (retrieval corpus = the targets of ``fold``, protocol A) with the derived columns."""
    cols = ', '.join(FEATURE_COLUMNS)
    derived = ', '.join(f'{expr} AS {name}' for name, expr in DERIVED.items())
    src = f"read_parquet('{feature_glob}', hive_partitioning=false)"
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE bq AS
    SELECT row_number() OVER (ORDER BY entity_id)::INT AS qid, {cols}, {derived}
    FROM (SELECT {cols} FROM {src} WHERE country = '{country}' AND entity_id IN (SELECT id FROM bench_q WHERE country = '{country}'))""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE tt AS
    SELECT row_number() OVER (ORDER BY entity_id)::INT AS tid, {cols}, {derived}
    FROM (SELECT {cols} FROM {src} WHERE country = '{country}' AND entity_id IN
          (SELECT entity_id FROM read_parquet('{manifest}') WHERE role = 'target' AND fold = '{fold}' AND country = '{country}'))""")
    con.execute('CREATE OR REPLACE TEMP TABLE cand (channel VARCHAR, qid INT, tid INT, rnk INT, score DOUBLE)')
    con.execute('CREATE OR REPLACE TEMP TABLE chan_stats (channel VARCHAR, seconds DOUBLE, pairs_before_cap BIGINT, oversize_blocks BIGINT, note VARCHAR)')
    return {'queries': con.execute('SELECT count(*) FROM bq').fetchone()[0], 'targets': con.execute('SELECT count(*) FROM tt').fetchone()[0]}


def equality_channel(con, name: str, expr: str, secondary: Optional[str] = None, cap: int = MAX_K) -> None:
    """Candidates = targets with the same non-empty key. A block larger than ``cap`` is ranked by ``secondary`` (SQL over aliases a=query, b=target)
    before truncation to MAX_K, so a common name is bounded but not silently dropped. Score = secondary similarity (1.0 without one)."""
    started = time.perf_counter()
    sec = secondary or '1.0'
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _j AS
    WITH qk AS (SELECT qid, {expr} AS k FROM bq WHERE {expr} IS NOT NULL AND {expr} <> ''),
         tk AS (SELECT tid, {expr} AS k FROM tt WHERE {expr} IS NOT NULL AND {expr} <> ''),
         blk AS (SELECT k, count(*) AS nt FROM tk GROUP BY k)
    SELECT qk.qid, tk.tid, blk.nt FROM qk JOIN blk USING (k) JOIN tk USING (k)""")
    pairs, oversize = con.execute(f"SELECT count(*), count(DISTINCT qid) FILTER (WHERE nt > {cap}) FROM _j").fetchone()
    con.execute(f"""
    INSERT INTO cand
    SELECT '{name}', qid, tid, row_number() OVER (PARTITION BY qid ORDER BY score DESC, tid)::INT AS rnk, score FROM (
        SELECT j.qid, j.tid, CASE WHEN j.nt > {cap} THEN {sec} ELSE 1.0 END AS score
        FROM _j j JOIN bq a ON a.qid = j.qid JOIN tt b ON b.tid = j.tid) QUALIFY rnk <= {MAX_K}""")
    con.execute(f"INSERT INTO chan_stats VALUES ('{name}', {time.perf_counter() - started}, {pairs}, {oversize or 0}, 'equality on {expr.replace(chr(39), '')[:80]}')")
    con.execute('DROP TABLE _j')


def postings_channel(con, name: str, tokens: str, df_cap: int, rarest: int = 6, min_shared: int = 1) -> None:
    """IDF-weighted inverted-index retrieval on a list column ``tokens`` (same column name on both sides).

    * vocabulary = tokens whose document frequency in the corpus is <= ``df_cap`` (stop-token cut-off);
    * each query keeps its ``rarest`` highest-IDF tokens; candidates = targets sharing >= ``min_shared`` of them;
    * score = sum of IDF over the shared tokens, computed in integer micro-units (exact, independent of thread scheduling), reported as a float;
      rank by (score desc, tid); MAX_K kept.
    """
    started = time.perf_counter()
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _pt AS
    SELECT DISTINCT tid, hash(tok) AS th FROM (SELECT tid, unnest({tokens}) AS tok FROM tt) WHERE tok <> ''""")
    con.execute("CREATE OR REPLACE TEMP TABLE _pv AS SELECT th, round(ln((n + 1.0) / (df + 0.5)) * 1000000)::BIGINT AS idf FROM (SELECT th, count(*) AS df FROM _pt GROUP BY th), "
                "(SELECT count(*) AS n FROM tt) WHERE df <= " + str(df_cap))
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _qt AS
    SELECT qid, th, idf FROM (
        SELECT qid, hash(tok) AS th FROM (SELECT DISTINCT qid, unnest({tokens}) AS tok FROM bq) WHERE tok <> '')
        JOIN _pv USING (th) QUALIFY row_number() OVER (PARTITION BY qid ORDER BY idf DESC, th) <= {rarest}""")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _sc AS
    SELECT q.qid, p.tid, sum(q.idf) AS score, count(*) AS shared FROM _qt q JOIN _pt p USING (th) GROUP BY 1, 2 HAVING count(*) >= {min_shared}""")
    pairs = con.execute('SELECT count(*) FROM _sc').fetchone()[0]
    con.execute(f"""
    INSERT INTO cand
    SELECT '{name}', qid, tid, row_number() OVER (PARTITION BY qid ORDER BY score DESC, tid)::INT AS rnk, score / 1000000.0 FROM _sc QUALIFY rnk <= {MAX_K}""")
    con.execute(f"INSERT INTO chan_stats VALUES ('{name}', {time.perf_counter() - started}, {pairs}, 0, 'postings df<={df_cap}, rarest={rarest}')")
    for t in ('_pt', '_pv', '_qt', '_sc'):
        con.execute(f'DROP TABLE {t}')


# ---------------------------------------------------------------------------------------------------------------- channel registry
ADDR_JACCARD = ("CASE WHEN len(a.a_toks) = 0 OR len(b.a_toks) = 0 THEN 0.0 ELSE len(list_intersect(a.a_toks, b.a_toks))::DOUBLE / "
                "len(list_distinct(list_concat(a.a_toks, b.a_toks))) END")
NAME_JW = "jaro_winkler_similarity(a.name_core, b.name_core)"

EQUALITY_CHANNELS: List[dict] = [
    # (B3 baseline) the two v1 exact-key joins
    {'name': 'eq_name_key', 'expr': 'name_key', 'secondary': ADDR_JACCARD, 'group': 'v1'},
    {'name': 'eq_address_key', 'expr': 'address_key', 'secondary': NAME_JW, 'group': 'v1'},
    # v2 cleaned views
    {'name': 'eq_name_core', 'expr': 'name_core', 'secondary': ADDR_JACCARD, 'group': 'v2'},
    {'name': 'eq_name_compact', 'expr': 'name_core_compact', 'secondary': ADDR_JACCARD, 'group': 'v2'},
    {'name': 'eq_address_tokset', 'expr': 'address_tokset', 'secondary': NAME_JW, 'group': 'v2'},
    {'name': 'eq_name_skeleton', 'expr': 'name_skeleton', 'secondary': ADDR_JACCARD, 'group': 'v2'},
    # secondary keys for common names: name plus one address anchor
    {'name': 'eq_core_postal', 'expr': "CASE WHEN postal1 IS NULL THEN NULL ELSE name_core || '|' || postal1 END", 'secondary': None, 'group': 'secondary'},
    {'name': 'eq_core_number', 'expr': "CASE WHEN num1 IS NULL THEN NULL ELSE name_core_compact || '|' || num1 END", 'secondary': None, 'group': 'secondary'},
    {'name': 'eq_skeleton_number', 'expr': "CASE WHEN num1 IS NULL THEN NULL ELSE name_skeleton || '|' || num1 END", 'secondary': None, 'group': 'secondary'},
]
POSTINGS_CHANNELS: List[dict] = [
    {'name': 'tok_name', 'tokens': 'n_toks', 'df_cap': 3000, 'rarest': 5, 'group': 'sparse'},
    {'name': 'tri_name', 'tokens': 'n_tri', 'df_cap': 5000, 'rarest': 10, 'group': 'sparse'},
    {'name': 'tok_address', 'tokens': 'a_toks', 'df_cap': 3000, 'rarest': 6, 'group': 'sparse'},
    {'name': 'bigram_address', 'tokens': 'a_bi', 'df_cap': 3000, 'rarest': 6, 'group': 'sparse'},
]


def run_all_channels(con, log=print) -> None:
    for spec in EQUALITY_CHANNELS:
        equality_channel(con, spec['name'], spec['expr'], spec['secondary'])
        log(f"    {spec['name']}: {con.execute('SELECT seconds FROM chan_stats WHERE channel = ?', [spec['name']]).fetchone()[0]:.1f}s")
    for spec in POSTINGS_CHANNELS:
        postings_channel(con, spec['name'], spec['tokens'], spec['df_cap'], spec['rarest'])
        log(f"    {spec['name']}: {con.execute('SELECT seconds FROM chan_stats WHERE channel = ?', [spec['name']]).fetchone()[0]:.1f}s")
