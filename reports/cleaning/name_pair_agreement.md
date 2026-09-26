# Name view agreement on true pairs (exploratory)

Exact agreement between the Source 1 reference name and its matched target name, 0.5% deterministic positive-pair sample. **Recall-side only**: collisions are in `name_view_collisions.csv`. Latin-script targets only.

X2 uses the shipped `appended_noise.tsv` (last-position share in S2/S3 >= 5x the S1 share and >= 3000 occurrences; unlabeled; fitted on train text for US/India and unlabeled test text for France).

- India: 6 tokens
- US: 24 tokens
- France: 7 tokens

| view | S2-India | S2-US | S3-India | S3-US |
|---|---|---|---|---|
| pairs (Latin targets) | 5639 | 11015 | 6935 | 11803 |
| v1 name_key | 18.7% | 26.4% | 18.7% | 25.8% |
| name_hyg | 19.2% | 27.9% | 19.2% | 27.1% |
| name_core | 59.5% | 53.1% | 54.2% | 48.2% |
| name_core_fold | 62.6% | 57.9% | 57.9% | 53.1% |
| name_core_set | 62.0% | 57.3% | 56.3% | 52.2% |
| name_core_compact | 63.3% | 56.5% | 58.1% | 51.2% |
| ANY of the four core views | 68.9% | 65.5% | 63.9% | 60.2% |
| X1 brackets dropped from core | 59.8% | 51.6% | 54.2% | 46.8% |
| X2 trailing appended-noise trimmed | 61.1% | 53.6% | 56.2% | 48.8% |
| X3 alias-aware (any core view OR alias part) | 68.9% | 65.5% | 66.8% | 63.7% |
| legal_form equal (info) | 67.0% | 72.1% | 67.0% | 75.2% |
| pairs whose target has an alias marker | 1 | 0 | 199 | 411 |
