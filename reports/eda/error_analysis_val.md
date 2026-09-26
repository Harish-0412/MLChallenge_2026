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
