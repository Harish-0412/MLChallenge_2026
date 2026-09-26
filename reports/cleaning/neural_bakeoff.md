# Neural cross-script bake-off (GPU)

**PROVISIONAL** (5% pair sample, no fold manifest yet). GPU: NVIDIA GeForce RTX 3050 6GB Laptop GPU, torch 2.14.0+cu126. 10,000 cross-script India query names; each must find its true Source 1 reference name among 479,954 unique S1 India `name_core` strings. Rank = expected rank under random tie-breaking.

| method | recall@1 | @10 | @50 | @100 | @500 | @1000 | median rank | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| skeleton | 64.4% | 82.8% | 93.2% | 95.9% | 98.4% | 99.0% | 1 | 0.719 |
| labse | 54.1% | 78.8% | 87.1% | 89.7% | 95.2% | 97.0% | 1 | 0.631 |
| e5-small | 25.9% | 49.6% | 62.1% | 67.0% | 76.2% | 80.1% | 11 | 0.343 |

## Candidate-set recall (percent of queries whose true S1 is in the union)

| budget per method | skeleton_only | labse_only | skeleton_or_labse | e5-small_only | skeleton_or_e5-small | skeleton_or_any_neural |
|---|---:|---:|---:|---:|---:|---:|
| top10 | 82.8% | 78.8% | 93.6% | 49.6% | 89.8% | 94.7% |
| top50 | 93.2% | 87.1% | 98.0% | 62.1% | 96.1% | 98.3% |
| top100 | 95.9% | 89.7% | 98.7% | 67.0% | 97.3% | 98.8% |
| top500 | 98.4% | 95.2% | 99.7% | 76.2% | 99.0% | 99.8% |

## Per script: skeleton

| script | queries | recall@10 | recall@100 |
|---|---:|---:|---:|
| Bengali | 630 | 77.3% | 94.4% |
| Devanagari | 5732 | 84.7% | 97.2% |
| Gujarati | 625 | 86.7% | 98.2% |
| Gurmukhi | 151 | 77.5% | 93.4% |
| Kannada | 794 | 88.5% | 97.7% |
| Malayalam | 389 | 75.6% | 91.5% |
| Oriya | 169 | 76.9% | 95.3% |
| Tamil | 699 | 63.4% | 83.0% |
| Telugu | 811 | 87.3% | 97.9% |

## Per script: labse

| script | queries | recall@10 | recall@100 |
|---|---:|---:|---:|
| Bengali | 630 | 72.5% | 86.0% |
| Devanagari | 5732 | 82.8% | 91.9% |
| Gujarati | 625 | 83.7% | 92.3% |
| Gurmukhi | 151 | 51.7% | 74.8% |
| Kannada | 794 | 77.3% | 89.4% |
| Malayalam | 389 | 72.0% | 88.2% |
| Oriya | 169 | 59.2% | 78.1% |
| Tamil | 699 | 57.5% | 78.7% |
| Telugu | 811 | 83.5% | 90.8% |

## Per script: e5-small

| script | queries | recall@10 | recall@100 |
|---|---:|---:|---:|
| Bengali | 630 | 31.9% | 53.2% |
| Devanagari | 5732 | 69.0% | 84.7% |
| Gujarati | 625 | 20.3% | 42.7% |
| Gurmukhi | 151 | 9.9% | 25.8% |
| Kannada | 794 | 23.2% | 45.8% |
| Malayalam | 389 | 38.8% | 63.0% |
| Oriya | 169 | 11.8% | 29.0% |
| Tamil | 699 | 6.4% | 15.9% |
| Telugu | 811 | 32.3% | 53.9% |

## Cost

| method | seconds | peak VRAM | names/s |
|---|---:|---:|---:|
| skeleton | 26.2 | - | - |
| labse | 62.6 | 3.79 | 7821 |
| e5-small | 35.3 | 2.42 | 13867 |
