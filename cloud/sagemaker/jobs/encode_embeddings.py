#!/usr/bin/env python3
"""GPU batch-scoring entry point: records -> normalized embedding shards."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from transformers import AutoModel, AutoTokenizer

from train_biencoder import mean_pool


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="/opt/ml/processing/input/model")
    parser.add_argument("--records", default="/opt/ml/processing/input/records")
    parser.add_argument("--output", default="/opt/ml/processing/output/embeddings")
    parser.add_argument("--text-column", default="name_core")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-length", type=int, default=192)
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModel.from_pretrained(args.model_path, local_files_only=True).to(device).eval()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    shard = 0
    for path in sorted(Path(args.records).rglob("*.parquet")):
        table = pq.read_table(path, columns=["entity_id", args.text_column])
        ids, texts = table["entity_id"].to_pylist(), table[args.text_column].to_pylist()
        vectors = []
        with torch.inference_mode():
            for offset in range(0, len(texts), args.batch_size):
                batch = tokenizer(texts[offset:offset + args.batch_size], padding=True, truncation=True,
                                  max_length=args.max_length, return_tensors="pt")
                batch = {key: value.to(device) for key, value in batch.items()}
                embedded = mean_pool(model(**batch).last_hidden_state, batch["attention_mask"])
                vectors.append(torch.nn.functional.normalize(embedded, dim=-1).cpu().numpy().astype("float32"))
        matrix = np.concatenate(vectors) if vectors else np.empty((0, model.config.hidden_size), dtype="float32")
        result = pa.table({"entity_id": ids, "embedding": pa.array(matrix.tolist(), type=pa.list_(pa.float32()))})
        pq.write_table(result, output / f"embeddings-{shard:05d}.parquet", compression="zstd")
        shard += 1
    if shard == 0:
        raise FileNotFoundError(f"no record Parquet files below {args.records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

