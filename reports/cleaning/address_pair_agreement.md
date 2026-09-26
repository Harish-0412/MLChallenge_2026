# Address view agreement on true pairs (exploratory, recall side)

Exact agreement / rates on the 0.5% deterministic positive-pair sample; denominator = pairs with a non-empty target address. Labels are used to report, not to fit: lexicons come from the unlabeled census.

| metric | S2-India | S2-US | S3-India | S3-US |
|---|---:|---:|---:|---:|
| pairs | 7063 | 10529 | 7606 | 11264 |
| v1 address_key | 12.2% | 14.3% | 4.3% | 4.8% |
| address_canon | 18.2% | 31.2% | 21.6% | 35.7% |
| address_tokset | 31.1% | 44.5% | 38.4% | 51.8% |
| address_segset | 28.5% | 44.4% | 37.5% | 51.6% |
| tokset Jaccard >= 0.8 | 73.4% | 56.7% | 61.2% | 67.0% |
| median tokset Jaccard | 0.90 | 0.83 | 0.88 | 1.00 |
| p10 tokset Jaccard | 0.60 | 0.56 | 0.36 | 0.60 |
| **state** |  |  |  |  |
| state: both found and equal | 98.6% | 99.3% | 98.5% | 99.2% |
| state: both found and DIFFERENT | 1.3% | 0.0% | 1.3% | 0.0% |
| state: target has none | 0.0% | 0.6% | 0.1% | 0.7% |
| **numbers** (pairs where both have spans) | 6249 | 9513 | 6637 | 10412 |
| numbers: share at least one | 89.2% | 86.2% | 88.8% | 89.3% |
| numbers: conflict (none shared) | 10.8% | 13.8% | 11.2% | 10.7% |
| city candidates overlap | 95.8% | 79.2% | 97.3% | 80.3% |
| India: target canon still has non-Latin tokens | 0.0% |  | 0.0% |  |
| **variants** |  |  |  |  |
| variant KEEP number labels: tokset equal | 30.2% | 44.5% | 37.3% | 51.8% |
| &nbsp;&nbsp;median Jaccard | 0.89 | 0.83 | 0.88 | 1.00 |
| variant keep injected components: tokset equal | 30.0% | 42.5% | 36.8% | 49.9% |
| &nbsp;&nbsp;median Jaccard | 0.89 | 0.83 | 0.88 | 0.91 |

## Rule ablation on true pairs (each row switches one group OFF)

Token-set equality / token-set Jaccard >= 0.8 / median Jaccard, on the same pairs. The row "default" is the shipped configuration.

| variant | S2-India | S2-US | S3-India | S3-US |
|---|---:|---:|---:|---:|
| default | 31.1% / 73.4% / 0.900 | 44.5% / 56.7% / 0.833 | 38.4% / 61.2% / 0.882 | 51.8% / 67.0% / 1.000 |
| without ct/hwy suffix_multi abbreviations | 31.1% / 73.4% / 0.900 | 43.4% / 55.2% / 0.833 | 38.4% / 61.2% / 0.882 | 50.6% / 65.3% / 1.000 |
| without India injected components (hn, b3, region, divreportingcircle) | 29.9% / 72.4% / 0.889 | 44.5% / 56.7% / 0.833 | 36.7% / 60.3% / 0.875 | 51.8% / 67.0% / 1.000 |
| without number label across a comma (Plot No, 93) | 31.1% / 73.4% / 0.900 | 44.5% / 56.7% / 0.833 | 38.4% / 61.2% / 0.882 | 51.8% / 67.0% / 1.000 |
