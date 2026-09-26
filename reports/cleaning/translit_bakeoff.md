# Transliteration bake-off (India cross-script true pairs)

**PROVISIONAL**: no fold manifest exists yet. Sample = deterministic 5% of all train labels; re-run with `--fold-manifest` on B's dev fold.

27,230 pairs; baseline v1-key ratio p10/p50/p90 = 8/10/15. Legal form (canonical code) agrees on 100.0% of pairs.

S1 India names sharing a key with another S1 name: name_core 53.6%, skeleton base 61.3%, coarse 66.2%.

## Overall (all scripts)

Ambiguity of the skeleton-equality channel = how many S1 India names share the key of an exact hit (mean / median / p95) and the share of hits whose key is unique among S1.

| engine | variant | us/name | p10 | p50 | >=80 | >=90 | exact | S1 rows per exact key mean/median/p95 | unique-key hits |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| anyascii | base | 4.0 | 66.7 | 85.7 | 69.8% | 34.3% | 19.3% | 64.02 / 57 / 126 | 9.0% |
| anyascii | coarse | 4.0 | 81.8 | 92.3 | 93.6% | 65.9% | 40.4% | 70.22 / 60 / 144 | 9.9% |
| anyascii_n | base | 6.4 | 73.7 | 88.9 | 80.6% | 45.7% | 24.7% | 64.23 / 57 / 130 | 9.4% |
| anyascii_n | coarse | 6.4 | 81.8 | 92.3 | 93.6% | 65.9% | 40.4% | 70.22 / 60 / 144 | 9.9% |
| itrans | base | 59.4 | 66.7 | 85.7 | 68.4% | 33.3% | 19.0% | 63.83 / 57 / 126 | 8.8% |
| itrans | coarse | 59.4 | 81.8 | 92.3 | 93.8% | 66.0% | 40.5% | 69.95 / 59 / 144 | 9.9% |
| hk | base | 36.3 | 66.7 | 83.3 | 64.8% | 30.9% | 17.1% | 61.28 / 56 / 119 | 8.2% |
| hk | coarse | 36.3 | 80.0 | 91.7 | 90.8% | 61.1% | 36.3% | 66.7 / 59 / 129 | 9.2% |
| iast | base | 50.0 | 66.7 | 85.7 | 68.6% | 33.4% | 19.1% | 64.0 / 57 / 126 | 8.8% |
| iast | coarse | 50.0 | 81.8 | 92.3 | 93.9% | 66.2% | 40.7% | 70.09 / 59 / 144 | 10.0% |

## Per script: anyascii|base

| script | pairs | p50 | >=80 | >=90 | exact |
|---|---:|---:|---:|---:|---:|
| Bengali | 1749 | 85.71428571428572 | 72.1% | 33.7% | 16.3% |
| Devanagari | 15412 | 85.71428571428572 | 68.5% | 33.1% | 19.7% |
| Gujarati | 1790 | 88.88888888888889 | 84.5% | 44.9% | 22.3% |
| Gurmukhi | 399 | 81.81818181818181 | 59.6% | 24.3% | 8.5% |
| Kannada | 2141 | 88.88888888888889 | 78.4% | 45.2% | 26.5% |
| Malayalam | 1077 | 85.71428571428572 | 72.8% | 29.0% | 17.0% |
| Oriya | 424 | 87.5 | 77.1% | 41.5% | 18.4% |
| Tamil | 1956 | 76.92307692307692 | 43.7% | 17.8% | 7.3% |
| Telugu | 2282 | 87.5 | 78.8% | 41.0% | 23.0% |

## Per script: anyascii|coarse

| script | pairs | p50 | >=80 | >=90 | exact |
|---|---:|---:|---:|---:|---:|
| Bengali | 1749 | 90.0 | 88.1% | 51.8% | 23.8% |
| Devanagari | 15412 | 92.85714285714286 | 95.8% | 68.1% | 42.5% |
| Gujarati | 1790 | 93.33333333333333 | 96.7% | 71.3% | 42.3% |
| Gurmukhi | 399 | 88.88888888888889 | 81.5% | 48.4% | 23.6% |
| Kannada | 2141 | 100.0 | 96.7% | 77.2% | 52.5% |
| Malayalam | 1077 | 90.0 | 86.6% | 52.8% | 29.4% |
| Oriya | 424 | 91.66666666666666 | 91.7% | 62.3% | 31.8% |
| Tamil | 1956 | 88.88888888888889 | 78.9% | 45.9% | 25.8% |
| Telugu | 2282 | 96.0 | 96.7% | 74.6% | 48.2% |
