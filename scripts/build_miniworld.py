"""Experimental 'mini-world' for the one-owner rule (NOT a frozen protocol).

The rule needs every competing query of a target to be present.  Take 10% of the validation queries and only the targets that are relevant to them:
all targets OWNED by the sampled queries plus 10% of the unmatched validation targets.  Every target's owner (if any) is then inside the world, so competition is
complete; the corpus is 10x smaller than the validation corpus, so retrieval is easier and absolute scores are optimistic.  Only the with/without-rule difference is
informative.  Writes data/splits/_mini_manifest.parquet (fold = 'mini' for members, 'x' otherwise).

    python scripts/build_miniworld.py
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet').as_posix()
OUT = (ROOT / 'data' / 'splits' / '_mini_manifest.parquet').as_posix()


def main() -> int:
    con = duckdb.connect()
    con.execute("SET threads=6; SET memory_limit='8GB'")
    con.execute(f"""
    CREATE TABLE m AS SELECT *, (hash('miniworld|' || entity_id) % 100) AS b FROM read_parquet('{MANIFEST}')
    WHERE fold = 'val' AND (role = 'query' OR assignment IN ('owner', 'unmatched_hash'))""")
    con.execute("""CREATE TABLE mq AS SELECT entity_id FROM m WHERE role = 'query' AND b < 10""")
    con.execute(f"""
    COPY (SELECT entity_id, role, source, country, CASE WHEN (role = 'query' AND b < 10) OR (role = 'target' AND assignment = 'owner' AND owner_id IN (SELECT entity_id FROM mq))
                                                        OR (role = 'target' AND assignment = 'unmatched_hash' AND b < 10) THEN 'mini' ELSE 'x' END AS fold,
                 stratum, match_count, owner_id, assignment
          FROM m) TO '{OUT}' (FORMAT PARQUET)""")
    r = con.execute(f"SELECT role, assignment, count(*) FROM read_parquet('{OUT}') WHERE fold = 'mini' GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    print('mini-world members:', r)
    return 0


if __name__ == '__main__':
    sys.exit(main())
