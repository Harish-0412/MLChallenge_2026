# Amazon ML Challenge 2026: pretraining workspace

Start with [the detailed two-person plan](docs/TEAM_PRETRAINING_PLAN.md).

- **Member A:** [data cleaning and record engineering](docs/MEMBER_A_DATA_CLEANING.md).
- **Member B:** [EDA, validation and candidate generation](docs/MEMBER_B_EDA_VALIDATION.md).
- **Measured results:** [full-data EDA findings](reports/eda/EDA_FINDINGS.md).

The first phase has parsed all 24,229,173 business records and all training labels, created raw-preserving Parquet copies with conservative comparison keys, and checked Unicode/text quality, label consistency and train/test overlap. Richer cleaning, frozen validation splits, actual retrieval benchmarking, hard-negative preparation and model training remain separate steps in the work plan.

## Reproduce

From this directory in PowerShell:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\audit_dataset.py --resume
.venv\Scripts\python.exe scripts\inspect_text_quality.py
.venv\Scripts\python.exe scripts\write_eda_findings.py
```

For a fresh machine, create a Python 3.12 virtual environment, install `requirements-eda.txt`, copy the supplied dataset into `student_resource/dataset/`, and omit `--resume` for the first audit. The shared plan contains exact setup commands.

The input TSVs are authoritative and unchanged. Derived Parquet files and the audit database are under `data/interim/`; they are excluded from Git. Only one process should write the database. Dependencies are pinned in `requirements-eda.txt`. Do not put datasets or multi-gigabyte derived caches in the final code archive.

`reports/eda/full_audit.json` stores input SHA-256 values and full-data counts. `verification.json` records post-run input checksums, Parquet row-count/content-fingerprint checks and sampled normalization parity. The `positive_pair_sample_*.csv` files are diagnostic samples, not validation folds or model-training data.

The earlier scripts in `tmp/` are exploratory history. Their word-character normalization can discard Indic combining marks; use the current tested scripts and measured report for ongoing work.

## Member A feature pipeline (Phases 0-6 implemented)

Details: [implementation plan](docs/MEMBER_A_IMPLEMENTATION_PLAN.md), [rule register](reports/eda/cleaning_decisions.md), [contract with Member B](reports/cleaning/contract_feat_v2_0.md), [input anomalies](reports/cleaning/input_anomalies.md). Code is in `src/cleaning/` (the v1 key in `scripts/normalization.py` is frozen); results are in `reports/cleaning/`.

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-features.txt
.venv\Scripts\python.exe -m unittest discover -s tests                     # 191 tests (~80 s)
.venv\Scripts\python.exe scripts\check_baseline.py                         # Phase 0: input hashes vs the audit
.venv\Scripts\python.exe scripts\build_manifest.py [--check]               # Phase 1: manifests\input_manifest_v1.json
.venv\Scripts\python.exe scripts\hygiene_report.py                         # Phase 2: full-data verification (~15 min)
.venv\Scripts\python.exe scripts\name_token_census.py                      # Phase 3 evidence (unlabeled)
.venv\Scripts\python.exe scripts\build_name_lexicons.py --write            # Phase 3/4 lexicons from curated lists + measured counts
.venv\Scripts\python.exe scripts\name_report.py                            # Phase 3+4: full-data verification + collision table (~22 min)
.venv\Scripts\python.exe scripts\name_eval_pairs.py                        # name-view agreement on true pairs (exploratory)
.venv\Scripts\python.exe scripts\native_legal_census.py                    # Phase 4 evidence: native-script legal words
.venv\Scripts\python.exe scripts\translit_bakeoff.py [--fold-manifest F]   # Phase 4 CPU bake-off (provisional until a fold exists)
.venv\Scripts\python.exe scripts\address_token_census.py                   # Phase 5 evidence (unlabeled)
.venv\Scripts\python.exe scripts\build_address_lexicons.py --write         # Phase 5 lexicons: curated definitions + measured counts (~3 min)
.venv\Scripts\python.exe scripts\address_eval_pairs.py                     # address-view agreement + rule ablation on true pairs (exploratory)
.venv\Scripts\python.exe scripts\build_features.py --version feat_v2_0_sample --max-groups 1   # Phase 6 sample build (~40 s)
.venv\Scripts\python.exe scripts\build_features.py                         # Phase 6 full build: 24,229,173 rows (~21 min, 6 workers)
.venv\Scripts\python.exe scripts\verify_features.py --version feat_v2_0    # Phase 6/7 verification of the built table (~25 min)
.venv\Scripts\python.exe scripts\address_extraction_sample.py              # 30 rows per country x source for hand review
```

Read the feature table with DuckDB (nothing else is needed; one row per entity, 69 columns, partitioned by split / source / country):

```python
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW feat AS SELECT * FROM read_parquet('data/features/feat_v2_0/**/*.parquet', hive_partitioning=true)")
con.execute("SELECT country, count(*) FROM feat WHERE split = 'test' AND source = 1 GROUP BY 1").fetchall()
```

A finished version directory is never overwritten (`build_features.py` refuses); a rule change creates a new version (`feat_v2_1`). `_manifest.json` records the input-manifest hash, the source-tree hash, the lexicon hashes, the schema and every file; `_run.json` records runtime, memory and libraries.

The GPU experiment runs in a separate environment (`.venv-gpu`, PyTorch CUDA build, ignored by Git): `.venv-gpu\Scripts\python.exe scripts\neural_bakeoff.py`. Optional bake-off dependency: `requirements-bakeoff.txt`.
