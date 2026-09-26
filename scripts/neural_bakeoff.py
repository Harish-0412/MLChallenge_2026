"""Phase 4 GPU candidate: neural cross-script name matching vs transliteration + skeleton (run with .venv-gpu).

    .venv-gpu\\Scripts\\python.exe scripts\\neural_bakeoff.py [--queries 10000] [--models labse e5-small]

Task (identical for every method): for each cross-script India true pair, rank the true Source 1 reference name among ALL unique
Source 1 India reference names (~480k). Both sides are the legal-form-free `name_core`. Methods:
  skeleton   graded similarity (RapidFuzz ratio) between coarse skeletons of the anyascii transliteration   [CPU]
  labse      cosine similarity of sentence-transformers/LaBSE embeddings (Apache-2.0, 471M parameters)       [GPU]
  e5-small   cosine similarity of intfloat/multilingual-e5-small embeddings (MIT, 118M parameters)            [GPU]
  fusion     true S1 is in the top-k of the skeleton list OR the top-k of the best neural list
Rank of the truth = 1 + (# candidates scoring higher) + (# other candidates with an equal score) / 2, i.e. the expected rank under random
tie-breaking, so coarse scores (skeleton keys) are not flattered by optimistic ties.

PROVISIONAL like the skeleton bake-off: deterministic 5% pair sample, no fold manifest yet. No business lookup, no external data:
only the supplied names are embedded; model weights are downloaded once into data/models/.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from rapidfuzz import fuzz, process  # noqa: E402

import translit_bakeoff as TB  # noqa: E402
from cleaning import names as N  # noqa: E402
from cleaning import translit as T  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'
MODELS = {'labse': ('sentence-transformers/LaBSE', ''), 'e5-small': ('intfloat/multilingual-e5-small', 'query: ')}
KS = (1, 5, 10, 50, 100, 500, 1000)


def expected_rank(greater, equal):
    return 1 + greater + (equal - 1) / 2.0


def summarize(ranks, scripts):
    ranks = np.asarray(ranks)
    out = {'median_rank': float(np.median(ranks)), 'mean_reciprocal_rank': float(np.mean(1.0 / ranks))}
    for k in KS:
        out[f'recall@{k}'] = round(100 * float(np.mean(ranks <= k)), 1)
    by = {}
    for s in sorted(set(scripts)):
        idx = [i for i, x in enumerate(scripts) if x == s]
        by[s] = {'n': len(idx), 'recall@10': round(100 * float(np.mean(ranks[idx] <= 10)), 1), 'recall@100': round(100 * float(np.mean(ranks[idx] <= 100)), 1)}
    out['per_script'] = by
    return out


def skeleton_ranks(queries, true_idx, choices):
    ranks = np.empty(len(queries))
    for start in range(0, len(queries), 250):
        chunk = queries[start:start + 250]
        scores = process.cdist(chunk, choices, scorer=fuzz.ratio, dtype=np.float32, workers=-1)
        true_scores = scores[np.arange(len(chunk)), true_idx[start:start + 250]]
        greater = (scores > true_scores[:, None]).sum(1)
        equal = (scores == true_scores[:, None]).sum(1)
        ranks[start:start + len(chunk)] = expected_rank(greater, equal)
    return ranks


def encode(model, texts, prefix, batch=512):
    return model.encode([prefix + t for t in texts], batch_size=batch, convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=False)


def neural_ranks(model, prefix, s1_texts, q_texts, true_idx):
    t0 = time.perf_counter()
    s1_emb = encode(model, s1_texts, prefix).float()
    q_emb = encode(model, q_texts, prefix).float()
    torch.cuda.synchronize()
    encode_seconds = time.perf_counter() - t0
    true = torch.as_tensor(true_idx, device=s1_emb.device)
    ranks = torch.empty(len(q_texts), device=s1_emb.device)
    for start in range(0, len(q_texts), 256):
        q = q_emb[start:start + 256]
        sims = q @ s1_emb.T
        t = sims[torch.arange(len(q), device=sims.device), true[start:start + 256]]
        greater = (sims > t[:, None]).sum(1)
        equal = (sims == t[:, None]).sum(1)
        ranks[start:start + len(q)] = 1 + greater + (equal - 1) / 2.0
    return ranks.cpu().numpy(), encode_seconds, len(s1_texts) + len(q_texts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--queries', type=int, default=10000)
    parser.add_argument('--models', nargs='+', default=list(MODELS), choices=list(MODELS))
    parser.add_argument('--limit-s1', type=int, default=0, help='smoke run: cap the S1 index size (writes nothing)')
    args = parser.parse_args()
    assert torch.cuda.is_available(), 'CUDA is not available in this environment'
    device = torch.cuda.get_device_name(0)
    print(f'device: {device}, torch {torch.__version__}, VRAM {torch.cuda.get_device_properties(0).total_memory / 2**30:.1f} GiB', flush=True)

    pairs, s1_names = TB.load_pairs(None, 'dev')
    pairs.sort(key=lambda r: (r[0], r[2]))
    step = max(1, len(pairs) // args.queries)
    pairs = pairs[::step][:args.queries]
    if args.limit_s1:
        s1_names = s1_names[:args.limit_s1]
        pairs = pairs[:200]
    print(f'{len(pairs):,} query pairs; {len(s1_names):,} S1 India names', flush=True)

    core_cache = {}
    def core_of(name):
        c = core_cache.get(name)
        if c is None:
            c = core_cache[name] = N.build_name_features(name, 'India')['name_core']
        return c
    cores = sorted({core_of(n) for n in s1_names} | {core_of(p[1]) for p in pairs})     # the true S1 of every query must be in the index
    core_index = {c: i for i, c in enumerate(cores)}
    skeletons = sorted({T.skeleton(T.to_ascii(c)) for c in cores})
    skel_index = {s: i for i, s in enumerate(skeletons)}
    q_native, q_skel, true_core_idx, true_skel_idx, scripts = [], [], [], [], []
    for s1_id, s1_name, t_id, t_name, source in pairs:
        f = N.build_name_features(t_name, 'India')
        q_native.append(f['name_core'])
        q_skel.append(f['name_skeleton'])
        true_core_idx.append(core_index[core_of(s1_name)])
        true_skel_idx.append(skel_index[T.skeleton(T.to_ascii(core_of(s1_name)))])
        scripts.append(next((s for s in T.script_names(f['name_scripts']) if s != 'Latin'), 'Other'))
    print(f'{len(cores):,} unique S1 cores, {len(skeletons):,} unique S1 skeletons', flush=True)

    results = {}
    t0 = time.perf_counter()
    skel_ranks = skeleton_ranks(q_skel, np.asarray(true_skel_idx), skeletons)
    results['skeleton'] = {**summarize(skel_ranks, scripts), 'seconds': round(time.perf_counter() - t0, 1), 'device': 'CPU (RapidFuzz, all cores)'}
    print('skeleton', {k: v for k, v in results['skeleton'].items() if k != 'per_script'}, flush=True)

    neural = {}
    from sentence_transformers import SentenceTransformer
    for key in args.models:
        name, prefix = MODELS[key]
        print(f'loading {name} ...', flush=True)
        model = SentenceTransformer(name, cache_folder=str(ROOT / 'data' / 'models'), device='cuda')
        model.half()
        torch.cuda.reset_peak_memory_stats()
        ranks, seconds, n = neural_ranks(model, prefix, cores, q_native, true_core_idx)
        neural[key] = ranks
        results[key] = {**summarize(ranks, scripts), 'seconds_to_encode_and_rank': round(seconds, 1), 'names_encoded_per_second': round(n / seconds),
                        'peak_vram_gib': round(torch.cuda.max_memory_allocated() / 2 ** 30, 2), 'device': device}
        print(key, {k: v for k, v in results[key].items() if k != 'per_script'}, flush=True)
        del model
        torch.cuda.empty_cache()

    fusion = {}
    for k in (10, 50, 100, 500):
        row = {'skeleton_only': round(100 * float(np.mean(skel_ranks <= k)), 1)}
        for key, ranks in neural.items():
            row[f'{key}_only'] = round(100 * float(np.mean(ranks <= k)), 1)
            row[f'skeleton_or_{key}'] = round(100 * float(np.mean((skel_ranks <= k) | (ranks <= k))), 1)
        if len(neural) > 1:
            best = np.minimum.reduce(list(neural.values()))
            row['skeleton_or_any_neural'] = round(100 * float(np.mean((skel_ranks <= k) | (best <= k))), 1)
        fusion[f'top{k}'] = row
    summary = {'provisional_sample_not_a_fold': True, 'queries': len(pairs), 'unique_s1_cores': len(cores), 'unique_s1_skeletons': len(skeletons),
               'gpu': device, 'torch': torch.__version__, 'results': results, 'fusion_recall_percent': fusion}
    print(json.dumps(fusion, indent=1))
    if args.limit_s1:
        print('smoke run: nothing written')
        return 0
    (OUT / 'neural_bakeoff.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    lines = ['# Neural cross-script bake-off (GPU)', '',
             f'**PROVISIONAL** (5% pair sample, no fold manifest yet). GPU: {device}, torch {torch.__version__}. {len(pairs):,} cross-script India query names; '
             f'each must find its true Source 1 reference name among {len(cores):,} unique S1 India `name_core` strings. Rank = expected rank under random tie-breaking.', '',
             '| method | recall@1 | @10 | @50 | @100 | @500 | @1000 | median rank | MRR |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key, r in results.items():
        lines.append(f"| {key} | {r['recall@1']}% | {r['recall@10']}% | {r['recall@50']}% | {r['recall@100']}% | {r['recall@500']}% | {r['recall@1000']}% | {r['median_rank']:.0f} | {r['mean_reciprocal_rank']:.3f} |")
    lines += ['', '## Candidate-set recall (percent of queries whose true S1 is in the union)', '', '| budget per method | ' + ' | '.join(next(iter(fusion.values()))) + ' |',
              '|---|' + '---:|' * len(next(iter(fusion.values())))]
    for k, row in fusion.items():
        lines.append(f'| {k} | ' + ' | '.join(f'{v}%' for v in row.values()) + ' |')
    for key, r in results.items():
        lines += ['', f'## Per script: {key}', '', '| script | queries | recall@10 | recall@100 |', '|---|---:|---:|---:|']
        lines += [f"| {s} | {v['n']} | {v['recall@10']}% | {v['recall@100']}% |" for s, v in r['per_script'].items()]
    lines += ['', '## Cost', '', '| method | seconds | peak VRAM | names/s |', '|---|---:|---:|---:|']
    for key, r in results.items():
        lines.append(f"| {key} | {r.get('seconds', r.get('seconds_to_encode_and_rank'))} | {r.get('peak_vram_gib', '-')} | {r.get('names_encoded_per_second', '-')} |")
    (OUT / 'neural_bakeoff.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print('wrote neural_bakeoff.md / .json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
