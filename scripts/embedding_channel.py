"""Multilingual embedding retrieval channel (LaBSE, Apache-2.0) for an existing candidate set: name embeddings, exact top-k by inner product on the GPU.

    .venv-gpu\\Scripts\\python.exe scripts\\embedding_channel.py --name val20k --corpus-fold val [--k 50] [--country India]

Same corpus and queries as scripts/build_candidate_set.py (protocol A: the targets of --corpus-fold; ``all`` = every training target), features only, no label.
Writes data/benchmarks/cand_<name>_emb.parquet (channel emb_name; columns channel, q, t, rnk, score, blk) which scripts/retrieval_gates.py can union with the
other channels.  Runs on the RTX 3050 for the validation corpora; use the DGX slice (23 GB) for the 8M-target dev corpus:
copy the repo + data, `pip install torch` (CUDA >= 12.8 build) + sentence-transformers, run with --corpus-fold dev.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet').as_posix()
FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0'
BENCH = ROOT / 'data' / 'benchmarks'
MODEL = 'sentence-transformers/LaBSE'


def encode(model, texts, batch=256):
    order = np.argsort([len(t) for t in texts])                   # sort by length: far less padding
    out = np.empty((len(texts), 768), dtype=np.float16)
    for start in range(0, len(texts), batch * 40):
        idx = order[start:start + batch * 40]
        emb = model.encode([texts[i] for i in idx], batch_size=batch, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        out[idx] = emb.astype(np.float16)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True)
    parser.add_argument('--corpus-fold', default='val')
    parser.add_argument('--k', type=int, default=50)
    parser.add_argument('--country', default='')
    parser.add_argument('--limit-corpus', type=int, default=0, help='debug: use only the first N corpus records (recall is then meaningless)')
    args = parser.parse_args()
    started = time.perf_counter()
    device = 'cuda'
    model = SentenceTransformer(MODEL, cache_folder=str(ROOT / 'data' / 'models'), device=device)
    model.half()
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='4GB'")
    fold_filter = '' if args.corpus_fold == 'all' else f"AND fold = '{args.corpus_fold}'"
    rows_out, info = [], {}
    for country in ([args.country] if args.country else ['India', 'US']):
        t0 = time.perf_counter()
        glob = (FEATURES / 'split=train' / 'source=*' / f'country={country}' / '*.parquet').as_posix()
        queries = con.execute(f"""SELECT f.entity_id, f.business_name FROM read_parquet('{glob}', hive_partitioning=false) f
                                  WHERE f.entity_id IN (SELECT id FROM read_parquet('{(BENCH / f'queries_{args.name}.parquet').as_posix()}') WHERE country = '{country}')
                                  ORDER BY f.entity_id""").fetchall()
        targets = con.execute(f"""SELECT f.entity_id, f.business_name FROM read_parquet('{glob}', hive_partitioning=false) f
                                  WHERE f.entity_id IN (SELECT entity_id FROM read_parquet('{MANIFEST}') WHERE role = 'target' {fold_filter} AND country = '{country}')
                                  ORDER BY f.entity_id""").fetchall()
        if args.limit_corpus:
            targets = targets[:args.limit_corpus]
        print(f'[{country}] {len(queries):,} queries, {len(targets):,} targets; encoding', flush=True)
        q_emb = torch.from_numpy(encode(model, [r[1] for r in queries])).to(device)
        t_emb = encode(model, [r[1] for r in targets])
        print(f'[{country}] encoded in {time.perf_counter() - t0:.0f}s; searching', flush=True)
        t_ids = np.array([r[0] for r in targets])
        k = min(args.k, len(targets))
        res_s, res_i = [], []
        t_gpu = torch.from_numpy(t_emb).to(device) if len(targets) <= 1_500_000 else None
        for q0 in range(0, len(queries), 512):                          # query blocks keep the similarity matrix small
            qb = q_emb[q0:q0 + 512]
            best_s = best_i = None
            for start in range(0, len(targets), 200_000):
                block = t_gpu[start:start + 200_000] if t_gpu is not None else torch.from_numpy(t_emb[start:start + 200_000]).to(device)
                s_, i_ = torch.topk((qb @ block.T).float(), min(k, block.shape[0]), dim=1)
                i_ = i_ + start
                if best_s is None:
                    best_s, best_i = s_, i_
                else:
                    s2, i2 = torch.cat([best_s, s_], 1), torch.cat([best_i, i_], 1)
                    best_s, sel = torch.topk(s2, k, dim=1)
                    best_i = torch.gather(i2, 1, sel)
            res_s.append(best_s)
            res_i.append(best_i)
        best_s, best_i = torch.cat(res_s), torch.cat(res_i)
        del t_gpu
        best_s, best_i = best_s.cpu().numpy(), best_i.cpu().numpy()
        for qi, (q, _n) in enumerate(queries):
            for rank in range(best_i.shape[1]):
                rows_out.append(('emb_name', q, t_ids[best_i[qi, rank]], rank + 1, float(best_s[qi, rank]), 0))
        info[country] = {'queries': len(queries), 'targets': len(targets), 'seconds': time.perf_counter() - t0}
        print(f'[{country}] done in {time.perf_counter() - t0:.0f}s', flush=True)
        torch.cuda.empty_cache()
    out = BENCH / f'cand_{args.name}_emb.parquet'
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({'channel': [r[0] for r in rows_out], 'q': [r[1] for r in rows_out], 't': [str(r[2]) for r in rows_out], 'rnk': pa.array([r[3] for r in rows_out], pa.int32()),
                      'score': [r[4] for r in rows_out], 'blk': pa.array([r[5] for r in rows_out], pa.int32())})
    pq.write_table(table, out.as_posix(), compression='zstd')
    (BENCH / f'cand_{args.name}_emb.json').write_text(json.dumps({'model': MODEL, 'k': args.k, 'corpus_fold': args.corpus_fold, 'info': info, 'seconds': time.perf_counter() - started}, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(rows_out):,} candidate rows -> {out.name} in {time.perf_counter() - started:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
