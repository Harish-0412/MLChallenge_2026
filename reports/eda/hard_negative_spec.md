# B6 - hard negatives: pair EDA, sampling specification and error analysis

Training pairs come from 50,000 dev queries retrieved from the dev-fold corpus (`pairs_train50k.parquet`): 15,546,154 candidate pairs, 168,081 true links (positive rate 1.08%); per query mean 310.9 candidates (p50 310, p99 456, max 569) and 3.36 true links; 5.86% of queries have no true link among their candidates.

## Retrieval strata (`evidence_slice`, the way a candidate was found)

| stratum | pairs | true links | positive rate | queries |
|---|---:|---:|---:|---:|
| cleaned_equal | 832,212 | 75,864 | 9.12% | 45,428 |
| exact_v1_key | 362,506 | 50,180 | 13.84% | 38,102 |
| sparse_address_only | 8,131,678 | 18,375 | 0.23% | 49,979 |
| sparse_name | 5,687,941 | 14,644 | 0.26% | 40,360 |
| skeleton_or_secondary | 531,817 | 9,018 | 1.70% | 27,577 |

## What makes a negative hard (lexical evidence a negative carries)

| kind | negatives | positives | positive rate |
|---|---:|---:|---:|
| A same cleaned name AND similar address | 7,200 | 84,698 | 92.17% |
| B same cleaned name, different address | 1,089,272 | 10,622 | 0.97% |
| C similar address, different name | 34,912 | 48,127 | 57.96% |
| D similar name and partly similar address | 11,050 | 9,901 | 47.26% |
| E one moderately similar field | 976,972 | 11,293 | 1.14% |
| F weak (retrieved by rare token or n-gram only) | 13,258,667 | 3,440 | 0.03% |

## Positive rate by the best sparse-channel rank

| best rank | pairs | positive rate |
|---|---:|---:|
| 1-3 | 365,126 | 32.20% |
| 11-20 | 1,460,017 | 0.32% |
| 4-10 | 971,230 | 3.51% |
| none/21+ | 12,749,781 | 0.09% |

## Sampling specification (`train_v1`)

**What the first classifier used:** every candidate of every training query, in its natural distribution, no subsampling and no sample weights (`sample_weight = 1`). This keeps the calibration of the probabilities intact, and macro-F0.5 on the held-out queries is 0.9708 (protocol A, small corpus).

**Rules that hold for any training set derived from these candidates:**

1. Unit of sampling = the query: all candidates of a query stay together, and a query is in exactly one of `fit`, `early-stop`, `calibration` (80/10/10 by hash of the id, salt `ranker-v1`), all inside the dev fold.
2. Positives = every true link that retrieval found. **A true link that retrieval missed is never turned into a negative and never injected** (recall loss stays visible in validation).
3. Negatives = the retrieved non-links (hard by construction: they were found by a name, address, skeleton, n-gram or embedding channel). A random-negative stratum is optional and only for calibration comparisons.
4. If the training set must be shrunk (memory, or the 10x larger dev corpus): keep all positives; keep per query at most 20 negatives, taking them in proportion to the strata above with all negatives of kinds A, C and D always kept (they are rare, about 53,000 of 15.4M negatives, and are the ones that decide precision), kind B (same cleaned name, different address: 1.09M negatives, positive rate 0.97%) capped at 8 per query, kinds E and F capped at 6 each per query keeping the best-ranked; store the inclusion probability and train with `sample_weight = 1 / probability`. Calibrate on an UNSAMPLED calibration slice, otherwise the probabilities are biased.
5. Excluded from features: ids, fold, truth cardinality, `match_count`, sampling weights, `evidence_slice`, any label-derived field. The allowlist is enforced by `ranking.pairs.assert_model_features` (tested).
6. Sampling must be a deterministic function of (seed, query id, target id); `modeling.sampling.sample_training_pairs` implements this and is tested. The down-sampled variant above is **specified but not trained**: the natural distribution was small enough to train on directly.

## Error analysis of the first classifier on held-out validation queries (val-B)

10,007 queries, 34,770 true links: 34,513 were retrieved as candidates (99.26%); the policy selected 32,833 of them and 462 false matches. **Macro-F0.5 = 0.9708.** Missed by retrieval: 257; retrieved but rejected: 1,680.

Loss decomposition (share of the 1.0 lost, averaged over all queries): singleton queries 0.0023 (4.17% of singletons received a false match), queries with true links 0.0269.

| stratum | pairs | true links | selected | TP | FP | retrieved but rejected |
|---|---:|---:|---:|---:|---:|---:|
| cleaned_equal | 50,953 | 15,300 | 15,026 | 14,889 | 137 | 411 |
| exact_v1_key | 19,749 | 10,081 | 10,091 | 10,021 | 70 | 60 |
| skeleton_or_secondary | 30,690 | 1,861 | 1,814 | 1,791 | 23 | 70 |
| sparse_address_only | 1,502,425 | 1,942 | 1,608 | 1,561 | 47 | 381 |
| sparse_name | 1,567,834 | 5,329 | 4,756 | 4,571 | 185 | 758 |

Retrieved-but-rejected links by error type of the link:

| error type | links |
|---|---:|
| 08 fuzzy name or address | 648 |
| 06 target address missing | 343 |
| 07 equal after v2 cleaning (name_core or address_canon) | 287 |
| 09 weak partial evidence | 226 |
| 04 cross-script target name | 86 |
| 02 exact name, address differs | 44 |
| 10 no shared textual evidence | 30 |
| 03 exact address, name differs | 16 |

False positives by calibrated probability: 0.5-0.7: 227, 0.7-0.9: 144, 0.9-1.0: 91. Share of false positives whose cleaned name equals the query's (name_core_ratio >= 95): 39.39%.

## Examples for hand review (raw text)

**False positives** (selected but not a true link): query name / address -> selected candidate name / address (probability)

- `S1-987828197` 'Bangalore Finance Pvt Ltd' | '1503 Tower 6 Hospalya Junction Salarpuria Cadenza Apartments Kudlu Gate, Bangalore, Karnataka' -> `S3-140462491` 'Bangalore Fínance Pvt Ltd' | '' (0.9300000071525574)
- `S1-975357807` 'Ridge Initiative' | '7230 261st Street, Stanwood, WA' -> `S3-981561628` 'Ridge [Initiative]' | '' (0.7450000047683716)
- `S1-225953642` 'Burge All Inc' | '3255 Arapaho Drive, Yucca, AZ' -> `S2-129357256` 'BURGE ÁLL' | '' (0.9440000057220459)
- `S1-365093941` 'High Impex Limited' | 'C/O Yudhishthir Ghosh, Khottadihi, Jamuria, Bardhaman, West Bengal' -> `S3-745932161` 'HIGH IMPEX PRIVATE LIMITED' | '' (0.9100000262260437)
- `S1-896167510` 'Maxim Institute of Technology' | 'Smt Manorama Devi Ashok Kumar Near Pani Illahibagh Opp Petrol Pump, Patna, Bihar' -> `S2-953518212` 'Maxim Maxim Institute' | 'NO 75 SMT MANORAMA DEVI ASHOK KUMAR NEAR PANI ILLAHIBAGH OPP PETROL PUMP, PATNA, Bihar' (0.5659999847412109)
- `S1-172898409` 'Buldhana Super Limited' | 'Nisarg Heights Apartment, Flat No.10, Buldhana, Maharashtra' -> `S3-207878255` 'Lyrarizaquoio' | 'Nisarg Heights Apartment, Flat No.10, Buldhana, Maharashtra' (0.6710000038146973)
- `S1-633215345` 'Diamond Asset Concepts Inc' | '630 Peachtree Lane, Kingston, TN' -> `S3-624763009` 'Glover Diamond Concepts Inc' | '' (0.6710000038146973)
- `S1-616924991` 'Christ Presbyterian Church' | '1108 Rowland Lane, Brookings, OR' -> `S2-349765839` 'Christ Presbyterian Church Clinic Corp' | '' (0.6710000038146973)
- `S1-179198293` 'Firefighters Local Union 749' | '73 Dawnlight Lane, Charleston, WV' -> `S2-201005736` 'Firefighters Union Local No' | '' (0.9100000262260437)
- `S1-115342514` 'Gulf Charities' | '53 Millham Street, Marlborough, MA' -> `S2-292103682` 'Gulf Charities V Inc' | '' (0.8090000152587891)
- `S1-746778804` 'Advanced Staffing Industries Corp' | '2030 26, Unit Apartment 200, Vestal, NY' -> `S2-94511572` 'ADVANCED STAFFING LNDUSTRIES' | '' (0.8090000152587891)
- `S1-132627794` 'Smart Data Brands LLC' | '1624 Grand Bay Drive, Oregon, OH' -> `S3-605744273` 'Smart Data Brhds LLC' | '' (0.9599999785423279)

**Retrieved but rejected true links**

- `S1-763748923` 'Alpha Hospitality' | 'Chandrasen Appt Cts 34/15 Fp 35/15 Prabhat Road Erandawane, Pune, Maharashtra' -> `S3-216107877` 'Alpha  Services' | '#0581 Chandrasen Appt Cts 34/15 Fp 35/15 Prabhat Road Erandawane, Pune, Deccan Gymkhana, MH' (0.4779999852180481)
- `S1-262784900` 'OA Liberty Tidewater' | '21170 Sanfilippo Road, Bridgeville, DE' -> `S2-525062627` 'OA Liberty' | 'SANFILIPPO ROAD, BRIDGEVILLE, DE' (0.38499999046325684)
- `S1-36426879` '24HR Towing, Inc.' | 'NC, Charlotte, 9813 Adison Gray Lane' -> `S2-435244853` 'HALOZETA' | 'ADISON GRAY LANE, CHARLOTTE, NC' (0.25999999046325684)
- `S1-641495347` 'Department of Motor Vehicles' | '908 36 Avenue, Saint Cloud, MN' -> `S3-622053855` 'Department of  Motor Vehicles Ventures' | '' (0.03500000014901161)
- `S1-208698343` 'Abagael Fisher Kongsberg Inc' | '300 Gene Moody Drive, San Benito, TX' -> `S3-206233402` 'Abagael Fisher Inc Center' | '318 Gene Moody Dr, San Benito, Texas' (0.09000000357627869)
- `S1-456014913` 'Quality Software Partners' | 'Unit Apartment 52, City Of Waukesha, 2715 University Drive, WI' -> `S2-83661693` 'Quality S0ftware Partners' | '' (0.3790000081062317)
- `S1-105762345` 'Bright Logistics Private Limited' | 'Ff/27, Aditya Complex, Manisagar Co Op Ho So Ltd Part-8, Opp Sal Hospital, Thaltej, Ahmedabad, Gujarat' -> `S2-431105947` 'Caloflux' | 'AHMEDABAD, ADITYA COMPLEX, MANISAGAR CO OP HO SO LTD PART-8, OPP SAL HOSPITAL, FF/27, ગુજરાત, THALTAJ' (0.2370000034570694)
- `S1-392956974` 'Jay It Private Limited' | 'B-242, First Floor Okhla, Industrial Area Phase-1, New Delhi, South Delhi, Delhi' -> `S3-803364848` 'Jay It Límited Private' | 'B-d/242, New Delhi, DL' (0.40299999713897705)
- `S1-912137146` 'Guru Consultancy Limited' | '0-1101/11 Tower B, Palm Village, Sector 126, Kharar, Rupnagar, Punjab' -> `S2-269293762` 'Mr Guru Limited Center' | '2-1101/11 TOWER B, PALM VILLAG, SECTOR 126, KHARAR, Punjab' (0.05900000035762787)
- `S1-40440028` 'Oakwood & Co' | 'Building No 5/3403/B21, Markaz Commercial Complex Second Floor, Indira Gandhi Road, Kozhikode, Kerala' -> `S3-143807656` 'Oaikwod and Có' | 'Building No C-5/3403/b21, Kozhikode, KL' (0.3790000081062317)
- `S1-209450372` 'Parnell Runway Inc' | '706 Audubon Street, Sac City, IA' -> `S3-34843838` 'Parnell Ruttynw Inc' | '707 Audubon St, Sac City, Iowa' (0.44699999690055847)
- `S1-171268020` 'Custom Staffing Partners LLC' | '2121 H Street, Unit 204, Washington, DC' -> `S2-229262557` 'Custom Staffing Partners' | '2120 H ST, WASHINGTON, DC' (0.3790000081062317)
