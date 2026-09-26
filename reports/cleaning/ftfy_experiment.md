# ftfy experiment (bounded, experiment only)

ftfy 6.3.1, default `fix_text` settings. Compared with the narrow rule `text_hygiene.clean_text`.

## Flagged fields (control/C1/SUB), 5,987 fields in all six files

- ftfy result equals the narrow rule after the v1 key: **5,853**; differs: **134**; ftfy left the string unchanged: **0**.
- Shapes: {'A-circ+C1': 4786, 'SUB': 709, 'a-circ+C1': 479, 'other control': 13}

- `test_source1` S1-114400399 (address, SUB): raw `'No.435, \x1aSaroja\x1a1St B Cross, 7Th Block, Koramangala, Bangalore, Karnataka'`; narrow rule `'No.435, Saroja 1St B Cross, 7Th Block, Koramangala, Bangalore, Karnataka'`; ftfy `'No.435, Saroja1St B Cross, 7Th Block, Koramangala, Bangalore, Karnataka'`
- `test_source1` S1-124163266 (address, SUB): raw `'Iii/124 A 1, 3Rd Floor, Black & White Enclave Tejus Nagar, Saly\x1aS Road, Near Rajagiri, School, Kalamassery P O, Ernakulam, Kerala'`; narrow rule `'Iii/124 A 1, 3Rd Floor, Black & White Enclave Tejus Nagar, Saly S Road, Near Rajagiri, School, Kalamassery P O, Ernakulam, Kerala'`; ftfy `'Iii/124 A 1, 3Rd Floor, Black & White Enclave Tejus Nagar, SalyS Road, Near Rajagiri, School, Kalamassery P O, Ernakulam, Kerala'`
- `test_source1` S1-178843460 (address, SUB): raw `'D\x1a122/6, 3Rd Floor Laxmi Nagar Near Primary School Vikas Marg, Delhi, East Delhi, Delhi'`; narrow rule `'D 122/6, 3Rd Floor Laxmi Nagar Near Primary School Vikas Marg, Delhi, East Delhi, Delhi'`; ftfy `'D122/6, 3Rd Floor Laxmi Nagar Near Primary School Vikas Marg, Delhi, East Delhi, Delhi'`
- `test_source1` S1-25571799 (address, SUB): raw `'Office Unit. No.207 2Nd Floor, Building \x1aRegent Prime\x1aNo.48 Whitefield Main Road, Bengaluru, Bangalore, Karnataka'`; narrow rule `'Office Unit. No.207 2Nd Floor, Building Regent Prime No.48 Whitefield Main Road, Bengaluru, Bangalore, Karnataka'`; ftfy `'Office Unit. No.207 2Nd Floor, Building Regent PrimeNo.48 Whitefield Main Road, Bengaluru, Bangalore, Karnataka'`
- `test_source1` S1-464188960 (address, SUB): raw `'Flat No.304, Elegant Heights, Officer\x1aS Campus Extension, Near Sirsi Road, Khatipura, Jaipur, Rajasthan'`; narrow rule `'Flat No.304, Elegant Heights, Officer S Campus Extension, Near Sirsi Road, Khatipura, Jaipur, Rajasthan'`; ftfy `'Flat No.304, Elegant Heights, OfficerS Campus Extension, Near Sirsi Road, Khatipura, Jaipur, Rajasthan'`
- `test_source1` S1-523932603 (address, SUB): raw `'Flat No 8, Siri\x1aS Lotus Bliss Apts, Plot No 3 Sy No 21&29, Kakatiya Hills, Guttalabegu, Mpet, Hyderabad, Telangana'`; narrow rule `'Flat No 8, Siri S Lotus Bliss Apts, Plot No 3 Sy No 21&29, Kakatiya Hills, Guttalabegu, Mpet, Hyderabad, Telangana'`; ftfy `'Flat No 8, SiriS Lotus Bliss Apts, Plot No 3 Sy No 21&29, Kakatiya Hills, Guttalabegu, Mpet, Hyderabad, Telangana'`
- `test_source1` S1-576710213 (address, SUB): raw `'134C, Noor\x1aS Complex, Velliyancheri Po Near Cheriparambu School, Edappatta, Malappuram, Malappuram, Malapuram, Kerala'`; narrow rule `'134C, Noor S Complex, Velliyancheri Po Near Cheriparambu School, Edappatta, Malappuram, Malappuram, Malapuram, Kerala'`; ftfy `'134C, NoorS Complex, Velliyancheri Po Near Cheriparambu School, Edappatta, Malappuram, Malappuram, Malapuram, Kerala'`
- `test_source1` S1-620613853 (address, SUB): raw `'302, Sai Nilayam Apartment, Besides Jagan\x1aS College, Gomathy Nagar, Magunta, Layout, Nellore, Andhra Pradesh'`; narrow rule `'302, Sai Nilayam Apartment, Besides Jagan S College, Gomathy Nagar, Magunta, Layout, Nellore, Andhra Pradesh'`; ftfy `'302, Sai Nilayam Apartment, Besides JaganS College, Gomathy Nagar, Magunta, Layout, Nellore, Andhra Pradesh'`

## Why ftfy and the narrow rule differ

In the differing rows U+001A is a *substituted apostrophe* (`NoorS Complex` = "Noor's Complex"), not a dash. The narrow rule turns it into a boundary, giving `noor s complex`, which is exactly what the v1 key gives for a real apostrophe; ftfy deletes it (`noors complex`), which would disagree with a counterpart that kept the apostrophe.

## Deterministic sample (includes some flagged rows): 100,944 rows (201,888 fields)

ftfy changed **73** fields. Characters it removed or replaced (top 12): `'’'` U+2019 x52, `'Â'` U+00C2 x15, `'\x80'` U+0080 x15, `'\x93'` U+0093 x12, `'\x1a'` U+001A x4, `'\x99'` U+0099 x3, `'¿'` U+00BF x2, `'ï'` U+00EF x2, `'½'` U+00BD x2

ftfy is a general normaliser (it also uncurls quotes, deletes some format characters and fixes widths). It is therefore NOT enabled in the pipeline: the narrow rule covers the only mojibake pattern present in the data, measured to have no effect on exact matching.
