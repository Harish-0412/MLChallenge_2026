"""Cross-encoder step 2 (GPU env): fine-tune multilingual-e5-small (MIT, 118M parameters) as a pair classifier and score the top-N pairs.

    .venv-gpu\\Scripts\\python.exe scripts\\ce_train.py [--max-train 300000] [--epochs 1]

Input text: 'query name | query address [SEP] candidate name | candidate address' (raw text).  Trains on data/benchmarks/ce_train.parquet (all positives + the
first-stage classifier's plausible negatives), then scores ce_cal.parquet and ce_val.parquet and writes data/benchmarks/ce_scores.parquet (q, t, split, ce_logit).
The validation and calibration queries never enter training.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'data' / 'benchmarks'
MAX_LEN = 96


def find_model() -> str:
    snap = sorted((ROOT / 'data' / 'models' / 'models--intfloat--multilingual-e5-small' / 'snapshots').iterdir())[0]
    return str(snap)


def batches(texts_a, texts_b, tok, size, device):
    for s in range(0, len(texts_a), size):
        enc = tok(list(texts_a[s:s + size]), list(texts_b[s:s + size]), truncation=True, max_length=MAX_LEN, padding=True, return_tensors='pt')
        yield s, {k: v.to(device) for k, v in enc.items()}


@torch.no_grad()
def score(model, tok, qs, ts, device, size=256):
    model.eval()
    order = np.argsort([len(a) + len(b) for a, b in zip(qs, ts)])
    out = np.empty(len(qs), dtype=np.float32)
    for s in range(0, len(order), size):
        idx = order[s:s + size]
        enc = tok([qs[i] for i in idx], [ts[i] for i in idx], truncation=True, max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
        with torch.autocast('cuda', dtype=torch.float16):
            out[idx] = model(**enc).logits.squeeze(-1).float().cpu().numpy()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-train', type=int, default=300_000)
    parser.add_argument('--epochs', type=int, default=1)
    parser.add_argument('--batch', type=int, default=64)
    parser.add_argument('--lr', type=float, default=5e-5)
    args = parser.parse_args()
    torch.manual_seed(20260926)
    rng = np.random.default_rng(20260926)
    device = 'cuda'
    tok = AutoTokenizer.from_pretrained(find_model())
    model = AutoModelForSequenceClassification.from_pretrained(find_model(), num_labels=1).to(device)
    train = pq.read_table(BENCH / 'ce_train.parquet').to_pydict()
    n = len(train['label'])
    label = np.array(train['label'])
    pos, neg = np.flatnonzero(label == 1), np.flatnonzero(label == 0)
    n_neg = max(args.max_train - len(pos), 0)
    # negatives: keep the first-stage classifier's most plausible ones (lowest rank) with priority, then fill randomly
    rank = np.array(train['rank'])
    hard = neg[np.argsort(rank[neg], kind='stable')][: n_neg // 2]
    rest = rng.choice(np.setdiff1d(neg, hard), size=min(n_neg - len(hard), len(neg) - len(hard)), replace=False)
    chosen = np.concatenate([pos, hard, rest])
    rng.shuffle(chosen)
    print(f'training pairs: {len(chosen):,} ({len(pos):,} positive, {len(hard) + len(rest):,} negative) of {n:,}', flush=True)
    qs = [train['q_text'][i] for i in chosen]
    ts = [train['t_text'][i] for i in chosen]
    y = torch.tensor(label[chosen], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(chosen) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.06, anneal_strategy='linear')
    scaler = torch.amp.GradScaler('cuda')
    loss_fn = torch.nn.BCEWithLogitsLoss()
    t0, step = time.perf_counter(), 0
    for epoch in range(args.epochs):
        model.train()
        perm = rng.permutation(len(chosen))
        for s in range(0, len(perm), args.batch):
            idx = perm[s:s + args.batch]
            enc = tok([qs[i] for i in idx], [ts[i] for i in idx], truncation=True, max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
            with torch.autocast('cuda', dtype=torch.float16):
                logits = model(**enc).logits.squeeze(-1)
            loss = loss_fn(logits.float(), y[idx].to(device))
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            step += 1
            if step % 500 == 0:
                print(f'step {step}/{steps} loss {loss.item():.4f} ({time.perf_counter() - t0:.0f}s)', flush=True)
    rows = []
    for split, fname in (('cal', 'ce_cal'), ('val', 'ce_val')):
        d = pq.read_table(BENCH / f'{fname}.parquet').to_pydict()
        t1 = time.perf_counter()
        s = score(model, tok, d['q_text'], d['t_text'], device)
        print(f'scored {split}: {len(s):,} pairs in {time.perf_counter() - t1:.0f}s', flush=True)
        rows.append(pa.table({'q': d['q'], 't': d['t'], 'split': [split] * len(s), 'ce_logit': s}))
    pq.write_table(pa.concat_tables(rows), (BENCH / 'ce_scores.parquet').as_posix(), compression='zstd')
    print(f'done; training + scoring {time.perf_counter() - t0:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
