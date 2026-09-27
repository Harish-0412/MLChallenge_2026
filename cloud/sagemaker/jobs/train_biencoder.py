#!/usr/bin/env python3
"""Offline/local-model multilingual bi-encoder contrastive training with Spot checkpoints."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pyarrow.parquet as pq
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer


class PairDataset(Dataset):
    def __init__(self, path: str | Path):
        table = pq.read_table(path, columns=["query_text", "target_text"])
        self.queries = table["query_text"].to_pylist()
        self.targets = table["target_text"].to_pylist()

    def __len__(self):
        return len(self.queries)

    def __getitem__(self, index):
        return self.queries[index], self.targets[index]


def mean_pool(hidden, attention_mask):
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(1) / mask.sum(1).clamp_min(1e-9)


def encode(model, tokenizer, texts, device, max_length):
    batch = tokenizer(list(texts), padding=True, truncation=True, max_length=max_length, return_tensors="pt")
    batch = {key: value.to(device) for key, value in batch.items()}
    vectors = mean_pool(model(**batch).last_hidden_state, batch["attention_mask"])
    return torch.nn.functional.normalize(vectors, dim=-1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="/opt/ml/input/data/base-model")
    parser.add_argument("--pairs", default="/opt/ml/input/data/train/pairs.parquet")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=192)
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModel.from_pretrained(args.model_path, local_files_only=True).to(device)
    loader = DataLoader(PairDataset(args.pairs), batch_size=args.batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    checkpoint = Path(os.environ.get("SM_CHECKPOINT_DIR", "/opt/ml/checkpoints"))
    checkpoint.mkdir(parents=True, exist_ok=True)
    state_path = checkpoint / "trainer.pt"
    start_epoch = 0
    if state_path.exists():
        state = torch.load(state_path, map_location=device, weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        start_epoch = state["epoch"] + 1
    model.train()
    for epoch in range(start_epoch, args.epochs):
        for queries, targets in loader:
            q = encode(model, tokenizer, queries, device, args.max_length)
            t = encode(model, tokenizer, targets, device, args.max_length)
            logits = q @ t.T / .05
            labels = torch.arange(len(q), device=device)
            loss = torch.nn.functional.cross_entropy(logits, labels)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            print(f"METRIC neural_loss={loss.item():.8g}", flush=True)
        torch.save({"epoch": epoch, "model": model.state_dict(), "optimizer": optimizer.state_dict()}, state_path)
    output = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output, safe_serialization=True)
    tokenizer.save_pretrained(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

